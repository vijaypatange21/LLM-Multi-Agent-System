"""
Routing policy engine for dynamic agent selection.

Routing policies decide which agents should execute based on:
- Query analysis
- Agent capabilities
- Context constraints
- Budget availability
- Performance history
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

from ..core import BaseAgent
from ..schemas import SharedContext
from .schemas import RoutingDecision, RoutingDecisionReason


class RoutingPolicy(ABC):
    """
    Abstract base class for routing policies.
    
    WHY: Different orchestration strategies may use different routing logic.
    Abstract policy enables:
    - Pluggable routing strategies
    - Testing (mock policies)
    - A/B testing routing approaches
    - Easy extension
    """
    
    @abstractmethod
    async def analyze_query(self, query: str, context: SharedContext) -> Dict[str, Any]:
        """
        Analyze query to extract intent, requirements, constraints.
        
        Returns:
            Dict with: intent, required_capabilities, constraints, budget_request
        """
        pass
    
    @abstractmethod
    async def score_agent(
        self,
        agent: BaseAgent,
        query: str,
        query_analysis: Dict[str, Any],
        context: SharedContext,
    ) -> Tuple[float, str]:
        """
        Score how well an agent matches this query.
        
        Returns:
            (score: 0-1, reasoning: why this score)
        """
        pass
    
    @abstractmethod
    async def rank_agents(
        self,
        query: str,
        agents: List[BaseAgent],
        query_analysis: Dict[str, Any],
        context: SharedContext,
    ) -> List[Tuple[BaseAgent, float, str]]:
        """
        Rank agents by suitability.
        
        Returns:
            List of (agent, score, reasoning) tuples, sorted by score descending
        """
        pass
    
    @abstractmethod
    async def select_agents(
        self,
        ranked_agents: List[Tuple[BaseAgent, float, str]],
        context: SharedContext,
        budget: float,
    ) -> Tuple[List[BaseAgent], List[RoutingDecision]]:
        """
        Select which agents to use based on ranking, budget, constraints.
        
        Returns:
            (selected_agents, routing_decisions)
        """
        pass


class CapabilityAnalysis(BaseModel):
    """Analysis of required capabilities from a query."""
    
    required_capabilities: List[str] = Field(
        description="Capabilities needed (e.g., search, database, calculation)"
    )
    optional_capabilities: List[str] = Field(
        default_factory=list,
        description="Nice-to-have capabilities"
    )
    excluded_agents: List[str] = Field(
        default_factory=list,
        description="Agents that should NOT be used"
    )
    agent_preferences: Dict[str, float] = Field(
        default_factory=dict,
        description="Preference scores for specific agents (0-1)"
    )


class QueryAnalysis(BaseModel):
    """Complete analysis of incoming query."""
    
    intent: str = Field(description="What is the user trying to do?")
    complexity: str = Field(description="simple, moderate, complex")
    estimated_steps: int = Field(description="How many steps to solve?")
    
    capabilities: CapabilityAnalysis = Field(description="Required capabilities")
    
    budget_request: Optional[float] = Field(
        default=None,
        description="Estimated budget needed"
    )
    time_sensitivity: str = Field(
        default="normal",
        description="realtime, fast, normal, background"
    )
    
    critical: bool = Field(
        default=False,
        description="Is this query critical? (don't skip steps)"
    )


class RuleBasedRoutingPolicy(RoutingPolicy):
    """
    Rule-based routing policy for dynamic agent selection.
    
    WHY: Rule-based routing is:
    - Interpretable: can explain why agent was selected
    - Tunable: rules can be updated without code changes
    - Testable: rules can be verified independently
    - Extensible: new rules can be added
    
    Rules consider:
    1. Query intent (what is user asking?)
    2. Agent capabilities (which agents can handle this?)
    3. Context constraints (any agents forbidden?)
    4. Budget (can we afford this agent?)
    5. Execution order (does this agent depend on others?)
    """
    
    # Capability mapping: query pattern -> (required_capabilities, optional_capabilities)
    CAPABILITY_MAP = {
        # Search-related
        "search": {
            "required": ["search"],
            "optional": ["summarize"],
            "agents": ["search_agent", "researcher_agent"],
        },
        "find": {
            "required": ["search"],
            "optional": ["filter"],
            "agents": ["search_agent", "researcher_agent"],
        },
        # Analysis
        "analyze": {
            "required": ["analyze"],
            "optional": ["summarize"],
            "agents": ["analyzer_agent", "reasoning_agent"],
        },
        "compare": {
            "required": ["analyze"],
            "optional": ["search"],
            "agents": ["analyzer_agent", "comparison_agent"],
        },
        # Data operations
        "calculate": {
            "required": ["compute"],
            "optional": ["search"],
            "agents": ["calculator_agent", "analyst_agent"],
        },
        "aggregate": {
            "required": ["compute"],
            "optional": ["database"],
            "agents": ["aggregator_agent", "analyst_agent"],
        },
        # Database
        "query_data": {
            "required": ["database"],
            "optional": ["search"],
            "agents": ["database_agent", "analyst_agent"],
        },
        # Synthesis
        "summarize": {
            "required": ["summarize"],
            "optional": ["search"],
            "agents": ["summarizer_agent", "writer_agent"],
        },
        "generate": {
            "required": ["summarize"],
            "optional": [],
            "agents": ["writer_agent", "generator_agent"],
        },
    }
    
    async def analyze_query(
        self,
        query: str,
        context: SharedContext,
    ) -> Dict[str, Any]:
        """
        Analyze query to extract intent and requirements.
        
        Simple implementation: keyword matching.
        Production: would use LLM or ML model.
        """
        query_lower = query.lower()
        
        # Extract intent from keywords
        intent = "general_query"
        required_capabilities = []
        optional_capabilities = []
        
        for keyword, capability_info in self.CAPABILITY_MAP.items():
            if keyword in query_lower:
                intent = keyword
                required_capabilities = capability_info["required"]
                optional_capabilities = capability_info["optional"]
                break
        
        # Estimate complexity
        complexity = "simple"
        if len(query) > 200:
            complexity = "complex"
        elif len(query) > 100:
            complexity = "moderate"
        
        # Determine time sensitivity
        time_sensitivity = "normal"
        urgent_keywords = ["immediately", "asap", "urgent", "quickly", "right now"]
        if any(kw in query_lower for kw in urgent_keywords):
            time_sensitivity = "realtime"
        
        return {
            "intent": intent,
            "required_capabilities": required_capabilities,
            "optional_capabilities": optional_capabilities,
            "complexity": complexity,
            "time_sensitivity": time_sensitivity,
            "is_critical": context.user_preferences.get("critical", False),
        }
    
    async def score_agent(
        self,
        agent: BaseAgent,
        query: str,
        query_analysis: Dict[str, Any],
        context: SharedContext,
    ) -> Tuple[float, str]:
        """
        Score agent's suitability for this query.
        
        Scoring factors:
        - Capability match (does agent have required skills?)
        - Performance history (does agent usually succeed?)
        - Cost efficiency (is agent cheap relative to capabilities?)
        """
        score = 0.5  # Baseline
        reasoning = []
        
        # Check capability match
        agent_tools = agent.get_available_tools()
        tool_names = [t.tool_type for t in agent_tools]
        
        required_caps = query_analysis.get("required_capabilities", [])
        for req_cap in required_caps:
            if req_cap in tool_names:
                score += 0.2
                reasoning.append(f"has {req_cap}")
        
        # Bonus for optional capabilities
        optional_caps = query_analysis.get("optional_capabilities", [])
        for opt_cap in optional_caps:
            if opt_cap in tool_names:
                score += 0.1
                reasoning.append(f"also has {opt_cap}")
        
        # Check if agent is in user preferences
        agent_prefs = context.user_preferences.get("agent_preferences", {})
        if agent.agent_id in agent_prefs:
            pref_score = agent_prefs[agent.agent_id]
            score = score * 0.7 + pref_score * 0.3
            reasoning.append(f"user prefers this agent ({pref_score})")
        
        # Cap score at 1.0
        score = min(1.0, score)
        
        return (score, " + ".join(reasoning) if reasoning else "baseline")
    
    async def rank_agents(
        self,
        query: str,
        agents: List[BaseAgent],
        query_analysis: Dict[str, Any],
        context: SharedContext,
    ) -> List[Tuple[BaseAgent, float, str]]:
        """Rank all agents by suitability."""
        rankings = []
        
        for agent in agents:
            score, reasoning = await self.score_agent(
                agent, query, query_analysis, context
            )
            rankings.append((agent, score, reasoning))
        
        # Sort by score descending
        rankings.sort(key=lambda x: x[1], reverse=True)
        
        return rankings
    
    async def select_agents(
        self,
        ranked_agents: List[Tuple[BaseAgent, float, str]],
        context: SharedContext,
        budget: float,
    ) -> Tuple[List[BaseAgent], List[RoutingDecision]]:
        """
        Select agents based on ranking, budget, constraints.
        
        Strategy:
        - Select top-ranked agents until budget exhausted
        - Always include required agents (from constraints)
        - Respect excluded agents
        """
        selected = []
        decisions = []
        remaining_budget = budget
        
        # Get constraints
        constraints = context.constraints or []
        required_agents = set()
        excluded_agents = set()
        
        for constraint in constraints:
            if constraint.constraint_type == "required_agents":
                required_agents.update(constraint.value)
            elif constraint.constraint_type == "excluded_agents":
                excluded_agents.update(constraint.value)
        
        # First pass: select required agents
        for agent, score, reasoning in ranked_agents:
            if agent.agent_id in required_agents:
                selected.append(agent)
                remaining_budget -= 0.1  # Assume minimal cost
                decisions.append(
                    RoutingDecision(
                        agent_id=agent.agent_id,
                        decision="SELECTED",
                        reason=RoutingDecisionReason.REQUIRED_BY_CONTEXT,
                        confidence=1.0,
                        explanation=f"Required by context: {reasoning}",
                        score=score,
                        alternative_agents=[],
                    )
                )
        
        # Second pass: select by ranking until budget exhausted
        for agent, score, reasoning in ranked_agents:
            if agent.agent_id in selected:
                continue  # Already selected
            
            if agent.agent_id in excluded_agents:
                decisions.append(
                    RoutingDecision(
                        agent_id=agent.agent_id,
                        decision="REJECTED",
                        reason=RoutingDecisionReason.CAPABILITY_MATCH,
                        confidence=1.0,
                        explanation="Excluded by context constraints",
                        score=score,
                        alternative_agents=[],
                    )
                )
                continue
            
            # Check budget
            if remaining_budget <= 0:
                decisions.append(
                    RoutingDecision(
                        agent_id=agent.agent_id,
                        decision="REJECTED",
                        reason=RoutingDecisionReason.CAPABILITY_MATCH,
                        confidence=1.0,
                        explanation="Insufficient budget",
                        score=score,
                        budget_available=False,
                        alternative_agents=[],
                    )
                )
                continue
            
            # Check score threshold (only select if reasonably good match)
            if score > 0.4:
                selected.append(agent)
                remaining_budget -= 0.1
                decisions.append(
                    RoutingDecision(
                        agent_id=agent.agent_id,
                        decision="SELECTED",
                        reason=RoutingDecisionReason.CAPABILITY_MATCH,
                        confidence=score,
                        explanation=f"Good match: {reasoning}",
                        score=score,
                        alternative_agents=[],
                    )
                )
        
        return (selected, decisions)
