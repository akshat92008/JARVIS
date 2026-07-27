"""
Synthetic Dataset Generator for Fine-Tuning jarvis-fable5-32b.
Generates structured training pairs containing:
- prompt: Software engineering / coding task.
- thinking: Deep Claude Fable 5 adaptive chain-of-thought (CoT) trace.
- completion: Production-grade multi-file solution with unit test assertions.
"""

import json
from pathlib import Path

DATASET_FILE = Path(__file__).parent.resolve() / "dataset_fable5.jsonl"

SAMPLE_TRAINING_EXAMPLES = [
    {
        "instruction": "Build a high-performance LRU Cache in Python with O(1) time complexity for get and put methods, thread safety, and unit tests.",
        "thinking": (
            "<<THINKING>>\n"
            "Task Analysis: Build a thread-safe LRU Cache in Python with O(1) operations.\n"
            "1. Data Structure Choice: Doubly Linked List + Hash Map (dictionary). Hash map stores key -> Node mapping for O(1) access.\n"
            "   Doubly linked list maintains access ordering (MRU at head, LRU at tail) for O(1) removal and insertion.\n"
            "2. Concurrency Control: Use `threading.Lock` or `threading.RLock` around dictionary and node manipulation methods.\n"
            "3. Edge Cases: Capacity = 0/1, duplicate put operations, accessing non-existent keys, thread concurrency race conditions.\n"
            "4. Testing Strategy: Create unit test suite testing basic operations, capacity bounds, and concurrent multi-threaded access.\n"
        ),
        "completion": (
            "<<FILES>>\n"
            "[\n"
            "  {\n"
            '    "path": "lru_cache.py",\n'
            '    "content": "import threading\\n\\nclass Node:\\n    def __init__(self, key=0, value=0):\\n        self.key = key\\n        self.value = value\\n        self.prev = None\\n        self.next = None\\n\\nclass LRUCache:\\n    def __init__(self, capacity: int):\\n        self.capacity = capacity\\n        self.cache = {}\\n        self.lock = threading.RLock()\\n        self.head = Node()\\n        self.tail = Node()\\n        self.head.next = self.tail\\n        self.tail.prev = self.head\\n\\n    def _remove(self, node: Node):\\n        prev_node = node.prev\\n        next_node = node.next\\n        prev_node.next = next_node\\n        next_node.prev = prev_node\\n\\n    def _add(self, node: Node):\\n        node.prev = self.head\\n        node.next = self.head.next\\n        self.head.next.prev = node\\n        self.head.next = node\\n\\n    def get(self, key: int) -> int:\\n        with self.lock:\\n            if key in self.cache:\\n                node = self.cache[key]\\n                self._remove(node)\\n                self._add(node)\\n                return node.value\\n            return -1\\n\\n    def put(self, key: int, value: int) -> None:\\n        with self.lock:\\n            if key in self.cache:\\n                self._remove(self.cache[key])\\n            node = Node(key, value)\\n            self.cache[key] = node\\n            self._add(node)\\n            if len(self.cache) > self.capacity:\\n                lru = self.tail.prev\\n                self._remove(lru)\\n                del self.cache[lru.key]\\n"'\n            "  },\n"
            "  {\n"
            '    "path": "test_lru_cache.py",\n'
            '    "content": "import unittest\\nfrom lru_cache import LRUCache\\n\\nclass TestLRUCache(unittest.TestCase):\\n    def test_lru_operations( me):\\n        cache = LRUCache(2)\\n        cache.put(1, 1)\\n        cache.put(2, 2)\\n        self.assertEqual(cache.get(1), 1)\\n        cache.put(3, 3)\\n        self.assertEqual(cache.get(2), -1)\\n\\nif __name__ == \'__main__\':\\n    unittest.main()\\n"'\n            "  }\n"
            "]\n"
            "<<TEST_COMMAND>>\n"
            "python -m unittest test_lru_cache.py"
        )
    }
]

def generate_synthetic_dataset():
    print(f"[Dataset Generator] Generating synthetic dataset -> {DATASET_FILE}")
    with open(DATASET_FILE, "w", encoding="utf-8") as f:
        for ex in SAMPLE_TRAINING_EXAMPLES:
            formatted = {
                "messages": [
                    {"role": "system", "content": "You are jarvis-fable5-32b, an autonomous software engineering AI model."},
                    {"role": "user", "content": ex["instruction"]},
                    {"role": "assistant", "content": f"{ex['thinking']}\n{ex['completion']}"}
                ]
            }
            f.write(json.dumps(formatted) + "\n")
    print(f"[Dataset Generator] Successfully saved synthetic training dataset.")

if __name__ == "__main__":
    generate_synthetic_dataset()
