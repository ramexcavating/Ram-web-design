import copy
from pathlib import Path

import pytest
import yaml

from ramfin import db
from ramfin.config import settings_from_dict

ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def settings(tmp_path):
    raw = yaml.safe_load((ROOT / "config" / "config.example.yaml").read_text())
    raw = copy.deepcopy(raw)
    raw["paths"]["data_dir"] = str(tmp_path / "data")
    raw["forecast"]["payroll"]["anchor_pay_date"] = "2026-08-14"
    return settings_from_dict(raw, tmp_path)


@pytest.fixture
def conn(settings):
    c = db.connect(":memory:")
    for code, desc, cat in [("01-100", "Mobilization", "GENERAL"), ("02-300", "Fuel - Equipment", "FUEL"), ("02-310", "Repairs & Maintenance", "REPAIRS"),
                            ("03-100", "Aggregate", "MATERIALS"), ("04-100", "Small tools & consumables", "SMALL_TOOLS"), ("09-100", "Office & software", "SOFTWARE")]:
        c.execute("INSERT INTO cost_codes(code, description, category) VALUES(?,?,?)", (code, desc, cat))
    for job, name, client, folder in [("240617", "MDM Kinchant", "MDM Construction", None), ("241115", "IDL Consulting", "IDL", "01_ACTIVE_PROJECTS/241115_IDL_CONSULTING_2024-2025"),
                                      ("260102", "Dunkley", "Dunkley Lumber", None)]:
        c.execute("INSERT INTO jobs(job_no, name, client, status, sharepoint_folder) VALUES(?,?,?,'active',?)", (job, name, client, folder))
    c.execute("INSERT INTO vendors(name, norm_name, category, critical, default_terms_days) VALUES('Four Rivers Co-operative','FOURRIVERS','fuel',1,30)")
    c.execute("INSERT INTO vendors(name, norm_name, category, critical, default_terms_days) VALUES('Online Curbing','ONLINECURBING','sub',0,30)")
    c.execute("INSERT INTO employees(name, position, base_rate) VALUES('Ed Smith','General Labourer',28.0)")
    c.commit()
    return c
