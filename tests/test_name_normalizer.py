from astra.graph.name_normalizer import NameNormalizer


def test_normalize_key_removes_separators_and_case():
    normalizer = NameNormalizer()

    assert normalizer.normalize_key("Auth_Service") == "authservice"
    assert normalizer.normalize_key("Auth-Service") == "authservice"
    assert normalizer.normalize_key("Auth Service") == "authservice"


def test_build_alias_map_groups_duplicate_semantic_names():
    normalizer = NameNormalizer()

    alias_map = normalizer.build_alias_map({
        "AuthService": ["a.py"],
        "Auth_Service": ["b.py"],
        "UserService": ["c.py"],
    })

    assert alias_map == {
        "authservice": ["a.py", "b.py"],
    }


def test_build_alias_map_ignores_unique_names():
    normalizer = NameNormalizer()

    alias_map = normalizer.build_alias_map({
        "AuthService": ["a.py"],
        "UserService": ["b.py"],
    })

    assert alias_map == {}
