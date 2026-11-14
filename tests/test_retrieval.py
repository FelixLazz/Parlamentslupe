from partei_hack.services.language import statement_features, stem
from partei_hack.services.matching import PassageMatcher


def test_german_inflections_are_matched_without_cloud():
    assert stem("investitionen") == stem("investition")
    matcher = PassageMatcher(
        [
            {
                "number": 4,
                "text": "Wir wollen öffentliche Investitionen in Schulen und Kommunen ermöglichen.",
            }
        ]
    )
    matches = matcher.match(
        {
            "label": "Investition in Schulen",
            "field_intro": "Öffentliche Investition für Schulen und Kommunen.",
        }
    )
    assert matches[0]["page"] == 4
    assert matches[0]["retrieval_method"] == "bm25-german-stems-concepts-v2"
    assert matches[0]["assessment"] == "not_assessable"


def test_conditions_numbers_and_negations_remain_review_features():
    features = statement_features(
        "Wenn die Finanzierung gesichert ist, werden wir bis 2030 "
        "nicht weniger als 20 Prozent fördern."
    )
    assert features["conditions"] == ["wenn"]
    assert "nicht" in features["negations"]
    assert features["years"] == ["2030"]
    assert "20 Prozent" in features["quantities"]
    assert features["review_required"]


def test_original_neighbor_context_and_duplicate_removal():
    text = (
        "Wenn die Finanzierung gesichert ist, gilt die folgende Zusage. "
        "Wir wollen Investitionen in Schulen und Kommunen wesentlich erhöhen. "
        "Dies gilt nicht für andere Maßnahmen."
    )
    matcher = PassageMatcher([{"number": 1, "text": text}, {"number": 2, "text": text}])
    matches = matcher.match(
        {
            "label": "Investitionen in Schulen",
            "field_intro": "Kommunen finanzieren Schulen.",
        }
    )
    assert matches[0]["context_before"].startswith("Wenn")
    assert matches[0]["context_after"].startswith("Dies gilt nicht")
    assert len([item for item in matcher.passages if "Wir wollen" in item["quote"]]) == 1


def test_generic_motion_word_cannot_link_unrelated_policies():
    matcher = PassageMatcher(
        [
            {
                "number": 1,
                "text": (
                    "Für eine Lockerung der Sanktionen gegen Russland gelten klare Bedingungen."
                ),
            }
        ]
    )
    assert (
        matcher.match(
            {
                "label": "Lockerung der Schuldenbremse",
                "field_intro": "Russland und die Ukraine werden in einer politischen Rede genannt.",
            }
        )
        == []
    )


def test_topics_alone_do_not_manufacture_two_strong_matches():
    matcher = PassageMatcher(
        [
            {
                "number": 1,
                "text": "Wir wollen Klimaschutz und Solaranlagen in allen Kommunen ausbauen.",
            }
        ]
    )
    assert (
        matcher.match(
            {
                "label": "Klimaschutz",
                "field_topics": [{"label": "Kommunen Solaranlagen ausbauen"}],
            }
        )
        == []
    )
