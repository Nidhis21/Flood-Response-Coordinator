"""
orchestrator.py — LangGraph Multi-Agent Orchestrator

This module defines the top-level supervisor graph that connects all 7 agents.
It uses LangGraph to map the flow of events between agents, while preserving
their ability to run as continuous async processes.
"""

import logging
import asyncio
from typing import TypedDict, Annotated, List, Dict, Any
import operator
from langgraph.graph import StateGraph, START, END

from backend.agents import perception, prediction, logistics, rescue, medical, liaison, conflict, movement_simulator

logger = logging.getLogger("orchestrator")

# We define the system state that the orchestrator monitors
class SystemState(TypedDict):
    active_events: Annotated[List[Dict[str, Any]], operator.add]
    health_status: Annotated[List[str], operator.add]

async def perception_node(state: SystemState):
    """Monitors physical sensors and APIs."""
    return {"health_status": ["perception_ok"]}

async def prediction_node(state: SystemState):
    """Processes perception data into flood alerts."""
    return {"health_status": ["prediction_ok"]}

async def logistics_node(state: SystemState):
    """Handles pre-positioning and resource management."""
    return {"health_status": ["logistics_ok"]}

async def rescue_node(state: SystemState):
    """Handles water rescue operations."""
    return {"health_status": ["rescue_ok"]}

async def medical_node(state: SystemState):
    """Handles medical triage and dispatch."""
    return {"health_status": ["medical_ok"]}

async def conflict_node(state: SystemState):
    """Resolves resource contention via priority auction."""
    return {"health_status": ["conflict_ok"]}

async def liaison_node(state: SystemState):
    """Handles outbound communication to citizens and officials."""
    return {"health_status": ["liaison_ok"]}


def build_system_graph():
    """
    Builds the LangGraph representation of the entire multi-agent system.
    This graph maps the conceptual flow:
    Environment -> Perception -> Prediction -> Logistics
    SOS Events -> Rescue/Medical -> Conflict -> Liaison
    """
    builder = StateGraph(SystemState)
    
    # Add all agent nodes
    builder.add_node("perception", perception_node)
    builder.add_node("prediction", prediction_node)
    builder.add_node("logistics", logistics_node)
    builder.add_node("rescue", rescue_node)
    builder.add_node("medical", medical_node)
    builder.add_node("conflict", conflict_node)
    builder.add_node("liaison", liaison_node)
    
    # Define the environment monitoring pipeline
    builder.add_edge(START, "perception")
    builder.add_edge("perception", "prediction")
    builder.add_edge("prediction", "logistics")
    
    # Define the emergency response pipeline
    builder.add_edge(START, "rescue")
    builder.add_edge(START, "medical")
    
    # Both rescue and medical can trigger conflict resolution
    builder.add_edge("rescue", "conflict")
    builder.add_edge("medical", "conflict")
    
    # All pipelines ultimately route outward via the community liaison
    builder.add_edge("logistics", "liaison")
    builder.add_edge("conflict", "liaison")
    
    builder.add_edge("liaison", END)
    
    return builder.compile()


class Orchestrator:
    def __init__(self):
        self.graph = build_system_graph()
        self.tasks = []
        logger.info("LangGraph Orchestrator initialized.")

    def start_all_agents(self):
        """Starts all 7 agents as background asyncio tasks."""
        logger.info("Starting all agent run loops via Orchestrator...")
        
        self.tasks = [
            asyncio.create_task(perception.run(), name="perception_agent"),
            asyncio.create_task(prediction.run(), name="prediction_agent"),
            asyncio.create_task(logistics.run(), name="logistics_agent"),
            asyncio.create_task(rescue.run(), name="rescue_agent"),
            asyncio.create_task(medical.run(), name="medical_agent"),
            asyncio.create_task(liaison.run(), name="liaison_agent"),
            asyncio.create_task(conflict.run(), name="conflict_agent"),
            asyncio.create_task(movement_simulator.run(), name="movement_simulator"),
        ]
        return self.tasks

    async def stop_all_agents(self):
        """Cancels all agent tasks gracefully."""
        for task in self.tasks:
            task.cancel()
        await asyncio.gather(*self.tasks, return_exceptions=True)
        logger.info("All agent tasks cancelled by Orchestrator.")

    async def run_diagnostics(self):
        """Periodically invoke the graph to check system mapping health."""
        while True:
            try:
                # Invoke the LangGraph representation of the system
                state = await self.graph.ainvoke({"active_events": [], "health_status": []})
                logger.info(f"Orchestrator graph cycle complete. Status: {state['health_status']}")
            except Exception as e:
                logger.error(f"Orchestrator diagnostic error: {e}")
            await asyncio.sleep(300)  # Check every 5 minutes

orchestrator = Orchestrator()
