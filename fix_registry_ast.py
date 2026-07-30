import ast
import sys

with open("jarvis/amaura/registry.py", "r") as f:
    source = f.read()

class AgentCallRewriter(ast.NodeTransformer):
    def visit_Call(self, node):
        self.generic_visit(node)
        if isinstance(node.func, ast.Name) and node.func.id == '_agent':
            if len(node.args) >= 1:
                agent_id_node = node.args[0]
                if isinstance(agent_id_node, ast.Constant) and isinstance(agent_id_node.value, str):
                    agent_id = agent_id_node.value
                    
                    # Remove any positional prompt_profile (it would be the 12th argument, index 11)
                    if len(node.args) == 12:
                        node.args.pop(11)
                        
                    # Remove any existing keyword argument for prompt_profile
                    node.keywords = [kw for kw in node.keywords if kw.arg != "prompt_profile"]
                    
                    # Add prompt_profile=agent_id
                    node.keywords.append(
                        ast.keyword(arg="prompt_profile", value=ast.Constant(value=agent_id))
                    )
        return node

tree = ast.parse(source)
rewriter = AgentCallRewriter()
new_tree = rewriter.visit(tree)

import astor
with open("jarvis/amaura/registry.py", "w") as f:
    f.write(astor.to_source(new_tree))
