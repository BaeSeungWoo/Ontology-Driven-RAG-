"""Temporary execution target; session ownership stays with the selected factory."""


def execution_target(factory_id, machine_code, mode=None, persona=None):
    if factory_id in {"yunam", "yulkok", "poongsan"} and (
        persona in {"maintenance", "engineer", "manager"}
        or mode in {"ladder", "electrical", "cms", "cms_manager"}
    ):
        return "yunam_origin", "M005"
    return factory_id, machine_code
