import sys
import os
import re

sys.path.append(".")
from jarvis.amaura.registry import ALL_AGENTS

PROMPTS_DIR = "jarvis/amaura/prompts"
os.makedirs(PROMPTS_DIR, exist_ok=True)

# 1. Read existing revenue_workforce.md
existing_content = ""
with open(os.path.join(PROMPTS_DIR, "revenue_workforce.md"), "r") as f:
    existing_content = f.read()

# Map the existing headings to actual agent IDs
mapping = {
    "Amaura Chief Revenue Officer Agent": "chief_revenue_officer",
    "Free Lead Discovery and Outreach Agent": "opportunity_scout",
    "Aggressive Sales Closer Agent": "sales_closer",
    "Amaura Marketing and Demand-Generation Agent": "marketing_head",
    "Master Revenue Workforce Orchestrator": "revenue_orchestrator",
}

# Split by heading and extract
sections = re.split(r"# \d+\.\s+", existing_content)[1:]  # skip intro

for section in sections:
    lines = section.split('\n')
    heading = lines[0].strip()
    
    # Extract the block in ```text ... ```
    content_match = re.search(r"```text\n(.*?)\n```", section, re.DOTALL)
    if content_match and heading in mapping:
        agent_id = mapping[heading]
        with open(os.path.join(PROMPTS_DIR, f"{agent_id}.md"), "w") as f:
            f.write(content_match.group(1).strip())
        print(f"Extracted {agent_id}.md")

# 2. Generate generic prompts for the rest
for agent in ALL_AGENTS:
    if agent.agent_id in mapping.values():
        continue
    
    prompt = f"""You are the {agent.name} of Amaura Labs.

COMPANY

Amaura Labs is an AI-native research and product engineering company.

Amaura builds:
- SaaS products
- AI applications
- mobile and web applications
- premium business websites
- internal business software
- developer tools
- startup MVPs

DEPARTMENT

You operate within the '{agent.department}' department.

PRIMARY OBJECTIVE

Your objective is to: {agent.objective}

RULES OF ENGAGEMENT

1. You are governed by strict execution bounds. Do not exceed your risk level ({agent.max_risk}).
2. You must achieve your objective efficiently. Your budget for this task is {agent.cost_limit_cents / 100:.2f} USD.
3. Only use your approved tools: {', '.join(agent.tools) if agent.tools else 'None'}.
4. Only access approved data boundaries: {', '.join(agent.data_access) if agent.data_access else 'None'}.
5. You report directly to: {agent.reviewer_id}. Do not self-certify your own work if it requires review.

PERFORMANCE METRICS

Your performance will be evaluated on the following metrics:
{chr(10).join(f"- {m}" for m in agent.performance_objectives)}
"""
    with open(os.path.join(PROMPTS_DIR, f"{agent.agent_id}.md"), "w") as f:
        f.write(prompt)
    print(f"Generated {agent.agent_id}.md")

