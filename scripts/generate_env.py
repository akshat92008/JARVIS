import os
import secrets
import stat

def generate_key():
    return secrets.token_urlsafe(32)

def load_env(filepath):
    env_vars = {}
    if os.path.exists(filepath):
        with open(filepath, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    k, v = line.split('=', 1)
                    env_vars[k.strip()] = v.strip()
    return env_vars

def main():
    old_env_path = '/Users/ashishsingh/Desktop/JARVIS/.env'
    example_env_path = '/Users/ashishsingh/Desktop/JARVIS/Amaura-Labs-Internal-Launch-Ready/.env.amaura.example'
    new_env_path = '/Users/ashishsingh/Desktop/JARVIS/.env.amaura'

    old_env = load_env(old_env_path)
    
    new_lines = []
    with open(example_env_path, 'r') as f:
        for line in f:
            stripped = line.strip()
            if not stripped or stripped.startswith('#') or '=' not in stripped:
                new_lines.append(line)
                continue
            
            k, v_example = stripped.split('=', 1)
            k = k.strip()
            v_example = v_example.strip()
            
            if k in old_env and old_env[k]:
                new_lines.append(f"{k}={old_env[k]}\n")
            elif v_example == 'replace-with-independent-random-value':
                new_lines.append(f"{k}={generate_key()}\n")
            else:
                new_lines.append(f"{k}={v_example}\n")
                
    with open(new_env_path, 'w') as f:
        f.writelines(new_lines)
        
    os.chmod(new_env_path, stat.S_IRUSR | stat.S_IWUSR)
    print("Created .env.amaura securely")

if __name__ == '__main__':
    main()
