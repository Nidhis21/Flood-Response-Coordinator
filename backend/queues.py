"""
queues.py — Asyncio queues for inter-agent communication.

No Redis, no external dependencies. All queues are in-process asyncio.Queue
instances. Each queue has a single producer pattern and one or more consumers.

Architecture:
  Perception → alert_queue → Prediction
  Community Liaison → sos_queue → Rescue, Medical
  Rescue, Medical → dispatch_queue → Community Liaison (SMS confirmation)
  Logistics → resource_update_queue → (broadcast / DB update)
  Rescue, Medical, Logistics → conflict_queue → Conflict Resolution
  Conflict Resolution → resolved_queue → all other agents
"""

import asyncio

class LazyQueue:
    def __init__(self):
        self._q = None

    @property
    def q(self):
        if self._q is None:
            self._q = asyncio.Queue()
        return self._q

    async def put(self, item):
        await self.q.put(item)

    async def get(self):
        return await self.q.get()

    def put_nowait(self, item):
        self.q.put_nowait(item)
        
    def get_nowait(self):
        return self.q.get_nowait()
        
    def task_done(self):
        self.q.task_done()

alert_queue = LazyQueue()
sos_queue = LazyQueue()
dispatch_queue = LazyQueue()
resource_update_queue = LazyQueue()
conflict_queue = LazyQueue()
resolved_queue = LazyQueue()
