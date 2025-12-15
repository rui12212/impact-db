import threading
from typing import Dict

# Dict to save the locks for each teacher
_teacher_locks: Dict[str, threading.Lock] = {}
# below is the lock to protect the lock itself
_teacher_locks_guard = threading.Lock()

def get_teacher_lock(teacher_page_id: str) -> threading.Lock:
    # fetch the Lock deends on the teacher_page_id
    with _teacher_locks_guard:
        lock = _teacher_locks.get(teacher_page_id)
        if lock is None:
            lock = threading.Lock()
            _teacher_locks[teacher_page_id] = lock
        return lock