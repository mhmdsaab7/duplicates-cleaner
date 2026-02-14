import os
import hashlib
import shutil
import queue
import threading
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

        self.mode_var = tk.StringVar(value="a_vs_b")  # within | a_vs_b | b_vs_a
        self.action_var = tk.StringVar(value="move")  # move | delete

        self.recursive_var = tk.BooleanVar(value=True)  # nested scan option
        self._scan_running = False
        self._worker_thread = None
        self._log_queue = queue.Queue()
        self._result_queue = queue.Queue()
        self._interactive_widgets = []

        self._build_ui()
        self.mode_var.trace_add("write", self._on_mode_change)
        self._sync_dir_b_visibility()

    def _build_ui(self):
        pad = {"padx": 10, "pady": 6}

        self.row1 = ttk.Frame(self)
        self.row1.pack(fill="x", **pad)
        ttk.Label(self.row1, text="Directory A:").pack(side="left")
        self.dir1_entry = ttk.Entry(self.row1, textvariable=self.dir1_var, width=70)
        self.dir1_entry.pack(side="left", padx=8)
        self.browse_a_btn = ttk.Button(
            self.row1,
            text="Browse...",
            command=lambda: self._browse(self.dir1_var)
        )
        self.browse_a_btn.pack(side="left")

        self.row2 = ttk.Frame(self)
        self.row2.pack(fill="x", **pad)
        ttk.Label(self.row2, text="Directory B:").pack(side="left")
        self.dir2_entry = ttk.Entry(self.row2, textvariable=self.dir2_var, width=70)
        self.dir2_entry.pack(side="left", padx=8)
        self.browse_b_btn = ttk.Button(
            self.row2,
            text="Browse...",
            command=lambda: self._browse(self.dir2_var)
        )
        self.browse_b_btn.pack(side="left")

        options = ttk.Frame(self)
        options.pack(fill="x", padx=10, pady=2)
        self.recursive_check = ttk.Checkbutton(
            options,
            text="Scan nested files (recursive)",
            variable=self.recursive_var
        )
        self.recursive_check.pack(anchor="w")

        modes = ttk.LabelFrame(self, text="Mode")
        modes.pack(fill="x", padx=10, pady=6)

        self.mode_a_vs_b_rb = ttk.Radiobutton(
            modes, text="Compare A vs B (remove duplicates from B)",
            variable=self.mode_var, value="a_vs_b"
        )
        self.mode_a_vs_b_rb.pack(anchor="w", padx=10, pady=2)

        self.mode_b_vs_a_rb = ttk.Radiobutton(
            modes, text="Compare B vs A (remove duplicates from A)",
            variable=self.mode_var, value="b_vs_a"
        )
        self.mode_b_vs_a_rb.pack(anchor="w", padx=10, pady=2)

        self.mode_within_rb = ttk.Radiobutton(
            modes, text="Within Directory A only",
            variable=self.mode_var, value="within"
        )
        self.mode_within_rb.pack(anchor="w", padx=10, pady=2)


        actions = ttk.LabelFrame(self, text="Action on duplicates")
        actions.pack(fill="x", padx=10, pady=6)

        self.action_move_rb = ttk.Radiobutton(
            actions, text="Move to _duplicates (safer)",
            variable=self.action_var, value="move"
        )
        self.action_move_rb.pack(anchor="w", padx=10, pady=2)

        self.action_delete_rb = ttk.Radiobutton(
            actions, text="Delete (dangerous)",
            variable=self.action_var, value="delete"
        )
        self.action_delete_rb.pack(anchor="w", padx=10, pady=2)

        btns = ttk.Frame(self)
        btns.pack(fill="x", padx=10, pady=10)
        self.scan_btn = ttk.Button(btns, text="Scan & Run", command=self.run)
        self.scan_btn.pack(side="left")
        self.clear_btn = ttk.Button(btns, text="Clear Log", command=self.clear_log)
        self.clear_btn.pack(side="left", padx=10)

        self.log = tk.Text(self, wrap="word")
        self.log.pack(fill="both", expand=True, padx=10, pady=10)
        self._interactive_widgets = [
            self.dir1_entry,
            self.dir2_entry,
            self.browse_a_btn,
            self.browse_b_btn,
            self.recursive_check,
            self.mode_within_rb,
            self.mode_a_vs_b_rb,
            self.mode_b_vs_a_rb,
            self.action_move_rb,
            self.action_delete_rb,
            self.scan_btn,
        ]

    def _on_mode_change(self, *_):
        self._sync_dir_b_visibility()

    def _sync_dir_b_visibility(self):
        if self.mode_var.get() == "within":
            if self.row2.winfo_manager():
                self.row2.pack_forget()
        else:
            if not self.row2.winfo_manager():
                self.row2.pack(fill="x", padx=10, pady=6, after=self.row1)

    def _browse(self, var):
        folder = filedialog.askdirectory()
        if folder:
            var.set(folder)

    def _set_scan_running(self, running: bool):
        self._scan_running = running
        state = "disabled" if running else "normal"
        for widget in self._interactive_widgets:
            widget.configure(state=state)
        self.scan_btn.configure(text="Running..." if running else "Scan & Run")

    def _enqueue_log(self, text: str):
        self._log_queue.put(text)

    def _drain_log_queue(self):
        chunks = []
        while True:
            try:
                chunks.append(self._log_queue.get_nowait())
            except queue.Empty:
                break

        if chunks:
            self.log.insert("end", "".join(chunks))
            self.log.see("end")

        try:
            result_kind, result_title, result_message = self._result_queue.get_nowait()
            self._finish_scan(result_kind, result_title, result_message)
            return
        except queue.Empty:
            pass

        if self._scan_running or not self._log_queue.empty():
            self.after(80, self._drain_log_queue)

    def log_line(self, s: str):
        self.log.insert("end", s)
        self.log.see("end")

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

    def _run_scan_worker(self, dir_a: str, dir_b: str, mode: str, action: str, recursive: bool):
        result_kind = "info"
        result_title = "Result"
        result_message = "No duplicates found."

        try:
            if mode == "within":
                self._enqueue_log(
                    f"Mode: Within A\nA: {dir_a}\nRecursive: {'ON' if recursive else 'OFF'}\n\n"
                )
                dups = find_duplicates_within(dir_a, recursive, self._enqueue_log)
                target_base = dir_a
            elif mode == "a_vs_b":
                self._enqueue_log(
                    f"Mode: Compare A vs B (remove from B)\n"
                    f"A (keep): {dir_a}\nB (remove): {dir_b}\n"
                    f"Recursive: {'ON' if recursive else 'OFF'}\n\n"
                )
                dups = find_duplicates_between(dir_a, dir_b, recursive, self._enqueue_log)
                target_base = dir_b
            else:
                self._enqueue_log(
                    f"Mode: Compare B vs A (remove from A)\n"
                    f"B (keep): {dir_b}\nA (remove): {dir_a}\n"
                    f"Recursive: {'ON' if recursive else 'OFF'}\n\n"
                )
                dups = find_duplicates_between(dir_b, dir_a, recursive, self._enqueue_log)
                target_base = dir_a

            if dups:
                if action == "move":
                    move_duplicates(dups, target_base, self._enqueue_log)
                    result_title = "Done"
                    result_message = f"Moved {len(dups)} duplicates to _duplicates."
                else:
                    delete_duplicates(dups, self._enqueue_log)
                    result_title = "Done"
                    result_message = f"Deleted {len(dups)} duplicates."
        except Exception as e:
            self._enqueue_log(f"[ERR] Unexpected error: {e}\n")
            result_kind = "error"
            result_title = "Error"
            result_message = f"Scan failed: {e}"

        self._result_queue.put((result_kind, result_title, result_message))

    def _finish_scan(self, result_kind: str, result_title: str, result_message: str):
        self._set_scan_running(False)
        self._drain_log_queue()
        if result_kind == "error":
            messagebox.showerror(result_title, result_message)
        else:
            messagebox.showinfo(result_title, result_message)

    def run(self):
        if self._scan_running:
            return

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

        while True:
            try:
                self._result_queue.get_nowait()
            except queue.Empty:
                break

        self.log_line("=== Duplicate File Remover ===\n\n")
        self._set_scan_running(True)
        self.after(80, self._drain_log_queue)
        self._worker_thread = threading.Thread(
            target=self._run_scan_worker,
            args=(dir_a, dir_b, mode, action, recursive),
            daemon=True,
        )
        self._worker_thread.start()


if __name__ == "__main__":
    App().mainloop()
