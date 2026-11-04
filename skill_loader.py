from pathlib import Path
import json
import yaml
import importlib.util


SKILLS_DIR=Path(__file__).parent / "skills"
agent_cache = {}

def load_skill_metadata() -> list[dict]:
    """扫描技能目录，读取各技能的名称和简介。"""
    skills = []

    for skill_file in SKILLS_DIR.glob("*/SKILL.md"):
        text=skill_file.read_text(encoding="utf-8")
        metadata = text.split("---", 2)[1]
        skills.append(yaml.safe_load(metadata))

    return skills

def load_skill(name:str)->str:
    """读取指定技能的详细指令，不包含元数据区。"""
    skill_file = SKILLS_DIR / name / "SKILL.md"
    text = skill_file.read_text(encoding="utf-8")
    return text.split("---", 2)[2].strip()

def load_agent(skill_name: str, class_name: str):
    if skill_name in agent_cache:
        return agent_cache[skill_name]

    agent_file = SKILLS_DIR / skill_name / "script" / "agent.py"

    spec = importlib.util.spec_from_file_location(
        f"{skill_name}_agent",
        agent_file,
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    agent_class = getattr(module, class_name)
    agent = agent_class()

    agent_cache[skill_name] = agent
    print(f"加载 Agent：{skill_name}")

    return agent


if __name__ == "__main__":
    print(json.dumps(
        load_skill_metadata(),
        ensure_ascii=False,
        indent=2,
    ))
