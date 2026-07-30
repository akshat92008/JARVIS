import re

with open("jarvis/amaura/registry.py", "r") as f:
    content = f.read()

# We want to find `_agent(\n        "agent_id",\n ... \n    )` and inject `prompt_profile="agent_id"` before the `)`
def replacer(match):
    full_match = match.group(0)
    agent_id = match.group(1)
    
    # If it already has prompt_profile, skip
    if "prompt_profile=" in full_match:
        return full_match
        
    # Find the last closing parenthesis of the _agent call
    # The regex captured up to `    ),`
    # We replace `    ),` with `        prompt_profile="agent_id",\n    ),`
    if full_match.endswith("    ),"):
        return full_match[:-6] + f'        prompt_profile="{agent_id}",\n    ),'
    return full_match

# Regex to match `_agent( ... "agent_id", ... )` block
pattern = r'    _agent\(\n\s+"([^"]+)",(?:.*?)(?:\n    \),)'
new_content = re.sub(pattern, replacer, content, flags=re.DOTALL)

with open("jarvis/amaura/registry.py", "w") as f:
    f.write(new_content)
