import os
import hashlib
import shutil
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

HASH_CHUNK_SIZE = 1024 * 1024  # 1MB


def file_hash(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while True:
            chunk = f.read(HASH_CHUNK_SIZE)
            if not chunk:
                break
            h.update(chunk)
    return h.hexdigest()


def iter_files(folder: str, recursive: bool):
    if recursive:
        for root, _, files in os.walk(folder):
            for name in files:
                full = os.path.join(root, name)
                if os.path.isfile(full):
                    yield full
    else:
        for name in os.listdir(folder):
            full = os.path.join(folder, name)
            if os.path.isfile(full):
                yield full


def build_index(folder: str, recursive: bool, log_cb):
    """
    Build a dict of (size, hash) -> representative_path for all files in folder.
    """
    index = {}
    files = list(iter_files(folder, recursive))
    log_cb(f"Indexing {len(files)} files in: {folder}\n")
    log_cb(f"Recursive scan: {'ON' if recursive else 'OFF'}\n")

    for i, path in enumerate(files, start=1):
        try:
            size = os.path.getsize(path)
            h = file_hash(path)
            key = (size, h)
            index.setdefault(key, path)  # keep first occurrence
            if i % 50 == 0:
                log_cb(f"  Progress: {i}/{len(files)}\n")
        except Exception as e:
            log_cb(f"[ERR] {path}: {e}\n")

    log_cb("Index complete.\n\n")
    return index


def find_duplicates_within(folder: str, recursive: bool, log_cb):
    """
    Find duplicates within one folder.
    Returns list of tuples (original_path, duplicate_path)
    """
    seen = {}  # (size, hash) -> original_path
    duplicates = []

    files = list(iter_files(folder, recursive))
    log_cb(f"Found {len(files)} files. Scanning within folder...\n")
    log_cb(f"Recursive scan: {'ON' if recursive else 'OFF'}\n\n")

    for i, path in enumerate(files, start=1):
        try:
            size = os.path.getsize(path)
            h = file_hash(path)
            key = (size, h)

            if key in seen:
                duplicates.append((seen[key], path))
                log_cb(f"[DUP] {path}\n  -> same as {seen[key]}\n")
            else:
                seen[key] = path

            if i % 50 == 0:
                log_cb(f"Progress: {i}/{len(files)}\n")
        except Exception as e:
            log_cb(f"[ERR] {path}: {e}\n")

    log_cb(f"\nDone. Duplicates found: {len(duplicates)}\n")
    return duplicates


def find_duplicates_between(keep_dir: str, remove_dir: str, recursive: bool, log_cb):
    """
    Compare remove_dir against keep_dir.
    Returns list of tuples (keep_path, remove_path) for duplicates found in remove_dir.
    """
    keep_index = build_index(keep_dir, recursive, log_cb)

    remove_files = list(iter_files(remove_dir, recursive))
    log_cb(
        f"Scanning {len(remove_files)} files in:\n  {remove_dir}\n"
        f"against keep-dir index...\n"
    )
    log_cb(f"Recursive scan: {'ON' if recursive else 'OFF'}\n\n")

    duplicates = []
    for i, path in enumerate(remove_files, start=1):
        try:
            size = os.path.getsize(path)
            h = file_hash(path)
            key = (size, h)

            if key in keep_index:
                duplicates.append((keep_index[key], path))
                log_cb(f"[DUP] {path}\n  -> same as {keep_index[key]}\n")

            if i % 50 == 0:
                log_cb(f"Progress: {i}/{len(remove_files)}\n")
        except Exception as e:
            log_cb(f"[ERR] {path}: {e}\n")

    log_cb(f"\nDone. Cross-dir duplicates found: {len(duplicates)}\n")
    return duplicates


def move_duplicates(dups, target_base_folder: str, log_cb):
    target = os.path.join(target_base_folder, "_duplicates")
    os.makedirs(target, exist_ok=True)

    moved = 0
    for keep_path, dup_path in dups:
        try:
            name = os.path.basename(dup_path)
            dest = os.path.join(target, name)

            if os.path.exists(dest):
                base, ext = os.path.splitext(name)
                k = 1
                while True:
                    dest = os.path.join(target, f"{base}({k}){ext}")
                    if not os.path.exists(dest):
                        break
                    k += 1

            shutil.move(dup_path, dest)
            moved += 1
            log_cb(f"[MOVE] {dup_path} -> {dest}\n")
        except Exception as e:
            log_cb(f"[ERR] moving {dup_path}: {e}\n")

    log_cb(f"\nMoved {moved} duplicate files to: {target}\n")


def delete_duplicates(dups, log_cb):
    deleted = 0
    for keep_path, dup_path in dups:
        try:
            os.remove(dup_path)
            deleted += 1
            log_cb(f"[DEL] {dup_path}\n")
        except Exception as e:
            log_cb(f"[ERR] deleting {dup_path}: {e}\n")

    log_cb(f"\nDeleted {deleted} duplicate files.\n")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Duplicate File Remover")
        self.geometry("900x580")

        self.dir1_var = tk.StringVar()
        self.dir2_var = tk.StringVar()

        self.mode_var = tk.StringVar(value="within")  # within | a_vs_b | b_vs_a
        self.action_var = tk.StringVar(value="move")  # move | delete

        self.recursive_var = tk.BooleanVar(value=True)  # nested scan option

        self._build_ui()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        row1 = ttk.Frame(self)
        row1.pack(fill="x", **pad)
        ttk.Label(row1, text="Directory A:").pack(side="left")
        ttk.Entry(row1, textvariable=self.dir1_var, width=70).pack(side="left", padx=8)
        ttk.Button(row1, text="Browse...", command=lambda: self._browse(self.dir1_var)).pack(side="left")

        row2 = ttk.Frame(self)
        row2.pack(fill="x", **pad)
        ttk.Label(row2, text="Directory B:").pack(side="left")
        ttk.Entry(row2, textvariable=self.dir2_var, width=70).pack(side="left", padx=8)
        ttk.Button(row2, text="Browse...", command=lambda: self._browse(self.dir2_var)).pack(side="left")

        options = ttk.Frame(self)
        options.pack(fill="x", padx=10, pady=2)
        ttk.Checkbutton(
            options,
            text="Scan nested files (recursive)",
            variable=self.recursive_var
        ).pack(anchor="w")

        modes = ttk.LabelFrame(self, text="Mode")
        modes.pack(fill="x", padx=10, pady=6)

        ttk.Radiobutton(
            modes, text="Within Directory A only",
            variable=self.mode_var, value="within"
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Radiobutton(
            modes, text="Compare A vs B (remove duplicates from B)",
            variable=self.mode_var, value="a_vs_b"
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Radiobutton(
            modes, text="Compare B vs A (remove duplicates from A)",
            variable=self.mode_var, value="b_vs_a"
        ).pack(anchor="w", padx=10, pady=2)

        actions = ttk.LabelFrame(self, text="Action on duplicates")
        actions.pack(fill="x", padx=10, pady=6)

        ttk.Radiobutton(
            actions, text="Move to _duplicates (safer)",
            variable=self.action_var, value="move"
        ).pack(anchor="w", padx=10, pady=2)

        ttk.Radiobutton(
            actions, text="Delete (dangerous)",
            variable=self.action_var, value="delete"
        ).pack(anchor="w", padx=10, pady=2)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        ttk.Button(btns, text="Scan & Run", command=self.run).pack(side="left")
        ttk.Button(btns, text="Clear Log", command=self.clear_log).pack(side="left", padx=10)

        self.log = tk.Text(self, wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=10)

    def _browse(self, var):
        folder = filedialog.askdirectory()
        if folder:
            var.set(folder)

    def log_line(self, s: str):
        self.log.insert("end", s)
        self.log.see("end")
        self.update_idletasks()

    def clear_log(self):
        self.log.delete("1.0", "end")

    def _confirm_delete(self):
        return messagebox.askyesno(
            "Confirm Delete",
            "This will permanently delete duplicate files.\n\nAre you sure?"
        )

    @staticmethod
    def _normalize_dir(path: str) -> str:
        return os.path.normcase(os.path.normpath(os.path.abspath(path)))

    def run(self):
        dir_a = self.dir1_var.get().strip()
        dir_b = self.dir2_var.get().strip()
        mode = self.mode_var.get()
        action = self.action_var.get()
        recursive = bool(self.recursive_var.get())

        if not dir_a or not os.path.isdir(dir_a):
            messagebox.showerror("Error", "Please select a valid Directory A.")
            return

        if mode in ("a_vs_b", "b_vs_a"):
            if not dir_b or not os.path.isdir(dir_b):
                messagebox.showerror("Error", "Please select a valid Directory B.")
                return

            a_norm = self._normalize_dir(dir_a)
            b_norm = self._normalize_dir(dir_b)
            if a_norm == b_norm:
                messagebox.showerror("Error", "Directory A and Directory B must be different.")
                return

        if action == "delete" and not self._confirm_delete():
            return

        self.log_line("=== Duplicate File Remover ===\n\n")

        if mode == "within":
            self.log_line(f"Mode: Within A\nA: {dir_a}\nRecursive: {'ON' if recursive else 'OFF'}\n\n")
            dups = find_duplicates_within(dir_a, recursive, self.log_line)
            target_base = dir_a
        elif mode == "a_vs_b":
            self.log_line(
                f"Mode: Compare A vs B (remove from B)\n"
                f"A (keep): {dir_a}\nB (remove): {dir_b}\n"
                f"Recursive: {'ON' if recursive else 'OFF'}\n\n"
            )
            dups = find_duplicates_between(dir_a, dir_b, recursive, self.log_line)
            target_base = dir_b
        else:
            self.log_line(
                f"Mode: Compare B vs A (remove from A)\n"
                f"B (keep): {dir_b}\nA (remove): {dir_a}\n"
                f"Recursive: {'ON' if recursive else 'OFF'}\n\n"
            )
            dups = find_duplicates_between(dir_b, dir_a, recursive, self.log_line)
            target_base = dir_a

        if not dups:
            messagebox.showinfo("Result", "No duplicates found.")
            return

        if action == "move":
            move_duplicates(dups, target_base, self.log_line)
            messagebox.showinfo("Done", f"Moved {len(dups)} duplicates to _duplicates.")
        else:
            delete_duplicates(dups, self.log_line)
            messagebox.showinfo("Done", f"Deleted {len(dups)} duplicates.")


if __name__ == "__main__":
    App().mainloop()
