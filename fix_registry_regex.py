import re

with open("jarvis/amaura/registry.py", "r") as f:
    content = f.read()

# For every `_agent(` call, we want to ensure `prompt_profile` is set to the agent ID.
# First, let's remove any positional prompt_profile string that is passed at the very end.
# We look for a line with just a string and a comma before the closing paren of _agent.
# Example: 
#         "marketing_demand_generation",
#     ),
content = re.sub(r'(\n\s+)"([a-z_]+)",(\n\s+\),)', r'\1prompt_profile="\2",\3', content)

# Next, for any _agent call that does NOT have prompt_profile=... before the closing paren, we add it.
def replacer(match):
    full_match = match.group(0)
    # the first arg is the agent ID
    agent_id = match.group(1)
    if "prompt_profile=" not in full_match:
        # replace the last `    ),` with `        prompt_profile="agent_id",\n    ),`
        # We can just look for `\n    ),` at the end
        if full_match.endswith("\n    ),"):
            return full_match[:-7] + f'\n        prompt_profile="{agent_id}",\n    ),'
    return full_match

pattern = r'    _agent\(\n\s+"([^"]+)",.*?\n    \),'
content = re.sub(pattern, replacer, content, flags=re.DOTALL)

with open("jarvis/amaura/registry.py", "w") as f:
    f.write(content)
