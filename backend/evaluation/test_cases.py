"""
Evaluation test cases: baseline, ambiguous, and adversarial.

Baseline: Clear, straightforward queries with unambiguous correct answers.
Ambiguous: Unclear requirements, multiple valid interpretations, missing context.
Adversarial: Designed to expose system weaknesses (hallucinations, contradictions, etc.).
"""

from typing import Dict, List
from uuid import uuid4

from backend.schemas import ContextMetadata, SharedContext
from .harness import CaseCategory, EvaluationCase


def _baseline_context(facts: Dict = None) -> SharedContext:
    """Helper to create baseline context."""
    return SharedContext(
        conversation_id=uuid4(),
        user_intent="answer a factual question",
        facts=facts or {},
        metadata=ContextMetadata(last_modified_by="evaluation"),
    )


def _ambiguous_context(facts: Dict = None, constraints: List = None) -> SharedContext:
    """Helper to create context with constraints."""
    
    constraint_list = constraints or []
    return SharedContext(
        conversation_id=uuid4(),
        user_intent="answer a question with context",
        facts=facts or {},
        constraints=constraint_list,
        metadata=ContextMetadata(last_modified_by="evaluation"),
    )


def create_baseline_cases() -> List[EvaluationCase]:
    """Create 5 baseline test cases."""
    
    cases = [
        EvaluationCase(
            id="baseline_001",
            category=CaseCategory.BASELINE,
            prompt="What are the main components of a transformer model?",
            context=_baseline_context({
                "retrieval_chunks": [
                    {
                        "chunk_id": "t1",
                        "source_id": "papers/transformer",
                        "source_title": "Attention Is All You Need",
                        "content": "Transformer models consist of an encoder and decoder. The encoder has multi-head attention and feed-forward layers. The decoder has similar layers plus cross-attention to the encoder.",
                    }
                ]
            }),
            expected_correctness="Transformer models have: 1) Encoder with multi-head attention and feed-forward layers 2) Decoder with self-attention, cross-attention, and feed-forward layers 3) Positional encoding",
            expected_citations=[
                {"claim": "multi-head attention", "source": "papers/transformer"},
                {"claim": "encoder-decoder architecture", "source": "papers/transformer"},
            ],
            constraints_to_check=[],
        ),
        
        EvaluationCase(
            id="baseline_002",
            category=CaseCategory.BASELINE,
            prompt="Summarize the key findings from the climate change report.",
            context=_baseline_context({
                "retrieval_chunks": [
                    {
                        "chunk_id": "c1",
                        "source_id": "reports/climate-2024",
                        "source_title": "IPCC Climate Report 2024",
                        "content": "Global temperatures have risen 1.2C since pre-industrial. Primary cause is greenhouse gas emissions. Key impacts include sea level rise, extreme weather, and ecosystem disruption.",
                    }
                ]
            }),
            expected_correctness="Key findings: Temperature rise of 1.2C since pre-industrial times, primary cause is greenhouse gas emissions, major impacts include sea level rise, extreme weather, and ecosystem disruption",
            expected_citations=[
                {"claim": "temperature rise 1.2C", "source": "reports/climate-2024"},
                {"claim": "greenhouse gas emissions", "source": "reports/climate-2024"},
            ],
            constraints_to_check=[],
        ),
        
        EvaluationCase(
            id="baseline_003",
            category=CaseCategory.BASELINE,
            prompt="How does photosynthesis work?",
            context=_baseline_context({
                "retrieval_chunks": [
                    {
                        "chunk_id": "b1",
                        "source_id": "biology/photosynthesis",
                        "source_title": "Photosynthesis Mechanisms",
                        "content": "Photosynthesis converts light energy into chemical energy. Light reactions occur in thylakoids and produce ATP and NADPH. Dark reactions in the stroma use ATP and NADPH to fix carbon dioxide into glucose.",
                    }
                ]
            }),
            expected_correctness="Photosynthesis has two stages: light reactions (in thylakoids, produce ATP and NADPH) and dark reactions/Calvin cycle (in stroma, use ATP and NADPH to produce glucose from CO2)",
            expected_citations=[
                {"claim": "light reactions in thylakoids", "source": "biology/photosynthesis"},
            ],
            constraints_to_check=[],
        ),
        
        EvaluationCase(
            id="baseline_004",
            category=CaseCategory.BASELINE,
            prompt="What is the capital of France?",
            context=_baseline_context({
                "facts": {"answer": "Paris", "country": "France"}
            }),
            expected_correctness="Paris is the capital of France",
            expected_citations=[],
            constraints_to_check=[],
        ),
        
        EvaluationCase(
            id="baseline_005",
            category=CaseCategory.BASELINE,
            prompt="Explain the water cycle.",
            context=_baseline_context({
                "retrieval_chunks": [
                    {
                        "chunk_id": "w1",
                        "source_id": "science/water",
                        "source_title": "Water Cycle",
                        "content": "Water evaporates from oceans and lakes into the atmosphere. It condenses into clouds. Precipitation returns water to earth as rain or snow. Water runs off into streams and rivers, returning to oceans.",
                    }
                ]
            }),
            expected_correctness="The water cycle includes: evaporation (water from oceans/lakes to atmosphere), condensation (forms clouds), precipitation (rain/snow), and runoff (back to oceans)",
            expected_citations=[
                {"claim": "evaporation and condensation", "source": "science/water"},
            ],
            constraints_to_check=[],
        ),
    ]
    
    return cases


def create_ambiguous_cases() -> List[EvaluationCase]:
    """Create 5 ambiguous test cases."""
    from backend.schemas.context import ContextConstraint
    
    cases = [
        EvaluationCase(
            id="ambiguous_001",
            category=CaseCategory.AMBIGUOUS,
            prompt="Summarize the impact of the policy and compare it with alternatives.",
            context=_ambiguous_context(
                facts={
                    "policy_name": "Carbon Tax",
                    "retrieval_chunks": [
                        {
                            "chunk_id": "p1",
                            "source_id": "policy/carbon-tax-2023",
                            "source_title": "Carbon Tax Implementation",
                            "content": "Carbon tax was implemented to reduce emissions. Initial data shows 5% emission reduction in first year.",
                        },
                        {
                            "chunk_id": "p2",
                            "source_id": "policy/alternative-a",
                            "source_title": "Cap and Trade Alternative",
                            "content": "Cap and trade systems limit overall emissions and allow trading. Studies show 3-7% emission reduction.",
                        }
                    ]
                },
                constraints=[
                    ContextConstraint(
                        name="comparison_required",
                        description="Must compare with at least one alternative",
                        constraint_type="requirement",
                        value={"min_alternatives": 1},
                    )
                ]
            ),
            expected_correctness="Carbon tax shows 5% emission reduction. Cap and trade shows 3-7% reduction. Both achieve emission goals through different mechanisms.",
            expected_citations=[
                {"claim": "5% emission reduction", "source": "policy/carbon-tax-2023"},
                {"claim": "3-7% emission reduction", "source": "policy/alternative-a"},
            ],
            expected_contradictions=["Different effectiveness ranges"],
            constraints_to_check=["comparison_required"],
            adversarial_goal="Handle multiple sources with different ranges",
        ),
        
        EvaluationCase(
            id="ambiguous_002",
            category=CaseCategory.AMBIGUOUS,
            prompt="Analyze the effectiveness of treatment X and consider side effects.",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "m1",
                            "source_id": "medical/treatment-x",
                            "source_title": "Treatment X Clinical Trial",
                            "content": "Treatment X improved patient outcomes in 80% of cases. Some patients reported side effects including fatigue and headaches.",
                        },
                        {
                            "chunk_id": "m2",
                            "source_id": "medical/treatment-x-long-term",
                            "source_title": "Long-term Effects Study",
                            "content": "Long-term follow-up shows side effects resolved in most patients. Overall effectiveness remains at 78% after 2 years.",
                        }
                    ]
                }
            ),
            expected_correctness="Treatment X is 80% effective initially, with side effects like fatigue and headaches. Long-term data shows 78% effectiveness with most side effects resolving.",
            expected_citations=[
                {"claim": "80% effectiveness", "source": "medical/treatment-x"},
                {"claim": "side effects resolve", "source": "medical/treatment-x-long-term"},
            ],
            expected_contradictions=["80% vs 78% effectiveness (time-dependent)"],
            constraints_to_check=[],
            adversarial_goal="Balance short and long-term conflicting data",
        ),
        
        EvaluationCase(
            id="ambiguous_003",
            category=CaseCategory.AMBIGUOUS,
            prompt="What is the best approach to X? Consider different perspectives.",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "v1",
                            "source_id": "debate/perspective-a",
                            "source_title": "Perspective A on X",
                            "content": "Approach A prioritizes efficiency and cost. It can achieve goals in 6 months with $10M budget.",
                        },
                        {
                            "chunk_id": "v2",
                            "source_id": "debate/perspective-b",
                            "source_title": "Perspective B on X",
                            "content": "Approach B prioritizes quality and sustainability. Takes 12 months but produces higher quality results.",
                        }
                    ]
                }
            ),
            expected_correctness="Approach A is faster and cheaper (6 months, $10M), but Approach B prioritizes quality over speed (12 months). Best approach depends on priorities.",
            expected_citations=[
                {"claim": "Approach A timeline", "source": "debate/perspective-a"},
                {"claim": "Approach B quality focus", "source": "debate/perspective-b"},
            ],
            expected_contradictions=["Speed vs Quality trade-off"],
            constraints_to_check=[],
            adversarial_goal="Acknowledge trade-offs without forcing false consensus",
        ),
        
        EvaluationCase(
            id="ambiguous_004",
            category=CaseCategory.AMBIGUOUS,
            prompt="What can we infer from the data?",
            context=_ambiguous_context(
                facts={
                    "data_snippet": "User engagement increased 15% month-over-month, but churn also increased 8%",
                }
            ),
            expected_correctness="Engagement up 15% but churn also up 8% suggests different user cohorts: new engaged users joining while some existing users leaving",
            expected_citations=[],
            expected_contradictions=["Simultaneous growth and churn"],
            constraints_to_check=[],
            adversarial_goal="Handle seemingly contradictory metrics",
        ),
        
        EvaluationCase(
            id="ambiguous_005",
            category=CaseCategory.AMBIGUOUS,
            prompt="Summarize the document and identify key recommendations.",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "r1",
                            "source_id": "report/executive-summary",
                            "source_title": "Executive Report",
                            "content": "Problem: System latency increased 30%. Recommendations: (a) scale infrastructure, (b) optimize queries, (c) upgrade database.",
                        }
                    ]
                }
            ),
            expected_correctness="Problem: 30% latency increase. Recommendations: infrastructure scaling, query optimization, database upgrade. Each addresses different root causes.",
            expected_citations=[
                {"claim": "latency increase", "source": "report/executive-summary"},
                {"claim": "recommendations", "source": "report/executive-summary"},
            ],
            expected_contradictions=[],
            constraints_to_check=[],
            adversarial_goal="Extract multiple recommendations without synthesizing prematurely",
        ),
    ]
    
    return cases


def create_adversarial_cases() -> List[EvaluationCase]:
    """Create 5 adversarial test cases designed to expose weaknesses."""
    
    cases = [
        EvaluationCase(
            id="adversarial_001",
            category=CaseCategory.ADVERSARIAL,
            prompt="Is treatment Y effective?",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "h1",
                            "source_id": "study/treatment-y-positive",
                            "source_title": "Treatment Y Positive Study",
                            "content": "Treatment Y was effective in 95% of cases in our clinical trial.",
                        },
                        {
                            "chunk_id": "h2",
                            "source_id": "study/treatment-y-meta-analysis",
                            "source_title": "Meta-Analysis of Treatment Y",
                            "content": "Meta-analysis of 20 studies shows Treatment Y is effective in only 45% of cases when controlling for publication bias.",
                        },
                        {
                            "chunk_id": "h3",
                            "source_id": "forum/patient-reviews",
                            "source_title": "Patient Reviews",
                            "content": "Patients report mixed results. Some say 'This drug saved my life' while others say 'Complete waste of money'.",
                        }
                    ]
                }
            ),
            expected_correctness="Treatment Y shows 95% effectiveness in one trial but only 45% in meta-analysis. Patient experiences are mixed. Effectiveness varies by individual factors.",
            expected_citations=[
                {"claim": "95% effectiveness", "source": "study/treatment-y-positive"},
                {"claim": "45% effectiveness meta-analysis", "source": "study/treatment-y-meta-analysis"},
            ],
            expected_contradictions=[
                "95% vs 45% effectiveness (study selection vs meta-analysis bias)",
                "Positive patient reviews vs negative reviews",
            ],
            constraints_to_check=[],
            adversarial_goal="Detect and address hallucination risk from conflicting sources",
        ),
        
        EvaluationCase(
            id="adversarial_002",
            category=CaseCategory.ADVERSARIAL,
            prompt="Did the policy reduce costs?",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "f1",
                            "source_id": "report/official",
                            "source_title": "Official Government Report",
                            "content": "Policy implementation reduced costs by 20% in year 1.",
                        },
                        {
                            "chunk_id": "f2",
                            "source_id": "analysis/independent",
                            "source_title": "Independent Analysis",
                            "content": "When accounting for one-time transition costs, actual cost reduction was only 5%.",
                        },
                        {
                            "chunk_id": "f3",
                            "source_id": "critique/false-accounting",
                            "source_title": "Critique of Accounting",
                            "content": "Official report excluded externalized costs. Total cost increase was 10% when externalities included.",
                        }
                    ]
                }
            ),
            expected_correctness="Official report claims 20% reduction, but accounting methods vary. Independent analysis shows 5% when including transition costs. Critique shows 10% increase including externalities.",
            expected_citations=[
                {"claim": "20% official reduction", "source": "report/official"},
                {"claim": "5% independent reduction", "source": "analysis/independent"},
                {"claim": "10% increase with externalities", "source": "critique/false-accounting"},
            ],
            expected_contradictions=[
                "20% vs 5% vs -10% depending on accounting method",
            ],
            constraints_to_check=[],
            adversarial_goal="Avoid being misled by accounting framing differences",
        ),
        
        EvaluationCase(
            id="adversarial_003",
            category=CaseCategory.ADVERSARIAL,
            prompt="Summarize the research findings.",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "r1",
                            "source_id": "research/study-a",
                            "source_title": "Study A",
                            "content": "Found correlation between X and Y with p-value 0.04.",
                        },
                        {
                            "chunk_id": "r2",
                            "source_id": "research/study-b",
                            "source_title": "Study B Replication",
                            "content": "Attempted replication of Study A. Could not reproduce findings. P-value 0.8.",
                        },
                        {
                            "chunk_id": "r3",
                            "source_id": "commentary/statistical",
                            "source_title": "Statistical Commentary",
                            "content": "Study A appears to be false positive due to p-hacking. Sample size too small.",
                        }
                    ]
                }
            ),
            expected_correctness="Study A found correlation but failed replication. Likely false positive due to small sample size and p-hacking. No reliable evidence of X-Y relationship.",
            expected_citations=[
                {"claim": "initial correlation", "source": "research/study-a"},
                {"claim": "failed replication", "source": "research/study-b"},
            ],
            expected_contradictions=[
                "Study A positive result vs Study B null result",
            ],
            constraints_to_check=[],
            adversarial_goal="Recognize failed replications and false positives",
        ),
        
        EvaluationCase(
            id="adversarial_004",
            category=CaseCategory.ADVERSARIAL,
            prompt="What is the cause of the problem?",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "c1",
                            "source_id": "analysis/cause-a",
                            "source_title": "Analysis: Cause A",
                            "content": "Root cause is insufficient resources. Recommend 50% budget increase.",
                        },
                        {
                            "chunk_id": "c2",
                            "source_id": "analysis/cause-b",
                            "source_title": "Analysis: Cause B",
                            "content": "Root cause is poor process design. Budget is not the issue. Recommend process redesign.",
                        },
                        {
                            "chunk_id": "c3",
                            "source_id": "analysis/cause-c",
                            "source_title": "Analysis: Cause C",
                            "content": "Root cause is leadership/culture. Money and process changes alone won't help.",
                        }
                    ]
                }
            ),
            expected_correctness="Three competing root cause theories: insufficient resources, poor process design, and organizational culture issues. Likely multiple factors. Single cause oversimplification would be incorrect.",
            expected_citations=[
                {"claim": "resource insufficiency theory", "source": "analysis/cause-a"},
                {"claim": "process design theory", "source": "analysis/cause-b"},
                {"claim": "culture theory", "source": "analysis/cause-c"},
            ],
            expected_contradictions=[
                "Three competing causal theories",
            ],
            constraints_to_check=[],
            adversarial_goal="Avoid false consensus on single cause when evidence suggests multiple factors",
        ),
        
        EvaluationCase(
            id="adversarial_005",
            category=CaseCategory.ADVERSARIAL,
            prompt="Should we adopt this recommendation?",
            context=_ambiguous_context(
                facts={
                    "retrieval_chunks": [
                        {
                            "chunk_id": "r1",
                            "source_id": "vendor/recommendation",
                            "source_title": "Vendor Recommendation",
                            "content": "Our solution will improve efficiency by 100% with 3x ROI in year 1.",
                        },
                        {
                            "chunk_id": "r2",
                            "source_id": "analysis/skeptical",
                            "source_title": "Skeptical Analysis",
                            "content": "Vendor claims are unrealistic. Industry benchmarks show 15-25% improvements. Hidden costs typically reduce ROI to 1.2x.",
                        },
                        {
                            "chunk_id": "r3",
                            "source_id": "case-study/similar-org",
                            "source_title": "Case Study from Similar Organization",
                            "content": "We tried similar solution. Got 18% improvement in first year but system stability issues required $2M additional investment.",
                        }
                    ]
                }
            ),
            expected_correctness="Vendor claims 100% improvement and 3x ROI, but industry benchmarks suggest 15-25% improvement with ~1.2x ROI after hidden costs. Case study shows 18% improvement but with additional stability costs.",
            expected_citations=[
                {"claim": "vendor claims", "source": "vendor/recommendation"},
                {"claim": "industry benchmarks", "source": "analysis/skeptical"},
                {"claim": "case study experience", "source": "case-study/similar-org"},
            ],
            expected_contradictions=[
                "Vendor optimistic claims vs realistic industry expectations",
            ],
            constraints_to_check=[],
            adversarial_goal="Detect vendor overselling and calibrate expectations",
        ),
    ]
    
    return cases
