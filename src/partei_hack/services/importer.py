"""Kontrollierter Legislaturimport mit explizitem Umfang und Importprotokoll."""

import json
from collections.abc import Callable
from typing import Any

from partei_hack.api.client import APIClient, APIError
from partei_hack.storage.database import Database, utc_now

VOTE_VALUES = {"yes", "no", "abstain", "no_show"}


def require_reference(payload: dict[str, Any], key: str, expected_id: int) -> None:
    ref = payload.get(key)
    if not isinstance(ref, dict) or ref.get("id") != expected_id:
        raise APIError(f"Filterprüfung fehlgeschlagen: {key} muss auf {expected_id} verweisen.")


class Importer:
    def __init__(self, client: APIClient, database: Database):
        self.client = client
        self.database = database

    def _single(self, resource: str, entity_id: int) -> dict[str, Any]:
        response = self.client.get_entity(resource, entity_id)
        entity = response.payload["data"]
        self.database.save_entity(resource, entity, response.source_url, response.fetched_at)
        return entity

    def _collection(
        self,
        resource: str,
        params: dict[str, Any],
        validate: Callable[[dict[str, Any]], None],
        *,
        limit: int | None = None,
    ) -> tuple[list[dict[str, Any]], int]:
        entities: list[dict[str, Any]] = []
        total = 0
        for page in self.client.iter_pages(resource, params, max_items=limit):
            total = page.total
            for entity in page.items:
                validate(entity)
            self.database.save_entities(resource, page.items, page.source_url, page.fetched_at)
            entities.extend(page.items)
        return entities, total

    def sync_period(
        self, period_id: int, *, max_polls: int | None = 5, with_votes: bool = False
    ) -> dict[str, Any]:
        if period_id < 1 or (max_polls is not None and max_polls < 1):
            raise ValueError("Perioden-ID und Begrenzung müssen positiv sein.")
        stats: dict[str, Any] = {
            "period_id": period_id,
            "with_votes": with_votes,
            "polls_complete": False,
            "votes": 0,
            "vote_polls_complete": 0,
        }
        run_id = self.database.start_import(
            period_id, {"max_polls": max_polls, "with_votes": with_votes}
        )
        try:
            period = self._single("parliament-periods", period_id)
            if period.get("type") != "legislature":
                raise APIError("sync-period benötigt eine Legislatur-ID, keine Wahl-ID.")

            def validate_mandate(entity: dict[str, Any]) -> None:
                require_reference(entity, "parliament_period", period_id)
                if entity.get("type") != "mandate":
                    raise APIError("Kandidatur statt Mandat erhalten.")

            mandates, _ = self._collection(
                "candidacies-mandates",
                {"parliament_period": period_id, "type": "mandate", "current_on": "all"},
                validate_mandate,
            )
            stats["mandates"] = len(mandates)
            mandate_ids = {item["id"] for item in mandates}
            fractions, _ = self._collection(
                "fractions",
                {"legislature": period_id},
                lambda item: require_reference(item, "legislature", period_id),
            )
            stats["fractions"] = len(fractions)
            polls, total = self._collection(
                "polls",
                {"field_legislature": period_id},
                lambda item: require_reference(item, "field_legislature", period_id),
                limit=max_polls,
            )
            stats.update(
                polls=len(polls),
                polls_available=total,
                polls_complete=len(polls) == total,
                poll_ids=sorted(poll["id"] for poll in polls),
            )
            if with_votes:
                for poll in polls:
                    self._import_poll_votes(poll, mandate_ids, stats)
            stats["programs"] = self._programs(period)
        except (Exception, KeyboardInterrupt) as exc:
            self.database.finish_import(run_id, stats, str(exc) or type(exc).__name__)
            raise
        self.database.finish_import(run_id, stats)
        return {"run_id": run_id, **stats}

    def _import_poll_votes(
        self,
        poll: dict[str, Any],
        mandate_ids: set[int],
        stats: dict[str, Any],
    ) -> None:
        poll_id = poll["id"]
        self.database.mark_vote_coverage(poll_id, None, complete=False)

        def validate_vote(entity: dict[str, Any], current_poll: int = poll_id) -> None:
            require_reference(entity, "poll", current_poll)
            mandate = entity.get("mandate")
            if not isinstance(mandate, dict) or mandate.get("id") not in mandate_ids:
                raise APIError("Stimme verweist nicht auf ein importiertes Mandat.")
            if entity.get("vote") not in VOTE_VALUES:
                raise APIError("Unbekannter Stimmenwert; keine automatische Umdeutung.")

        votes, expected = self._collection("votes", {"poll": poll_id}, validate_vote)
        self.database.save_entity(
            "vote-import-manifests",
            {
                "id": poll_id,
                "label": f"Vote-ID-Satz für Poll {poll_id}",
                "vote_ids": sorted(vote["id"] for vote in votes),
                "expected_count": expected,
            },
            poll.get("api_url") or f"poll:{poll_id}",
            utc_now(),
        )
        self.database.mark_vote_coverage(poll_id, expected, complete=True)
        stats["votes"] += len(votes)
        stats["vote_polls_complete"] += 1

    def import_poll_metadata(self, period_id: int) -> dict[str, Any]:
        """Vollständige Titelliste, ohne Mandate, Einzelstimmen oder Programme."""
        stats: dict[str, Any] = {"metadata_only": True, "polls_complete": False}
        run_id = self.database.start_import(period_id, {"metadata_only": True})
        try:
            polls, total = self._collection(
                "polls",
                {"field_legislature": period_id},
                lambda item: require_reference(item, "field_legislature", period_id),
            )
            stats.update(
                polls=len(polls),
                polls_available=total,
                polls_complete=len(polls) == total,
                poll_ids=sorted(poll["id"] for poll in polls),
            )
        except (Exception, KeyboardInterrupt) as exc:
            self.database.finish_import(run_id, stats, str(exc) or type(exc).__name__)
            raise
        self.database.finish_import(run_id, stats)
        return {"run_id": run_id, **stats}

    def import_votes(
        self, period_id: int, poll_ids: list[int], *, refresh_mandates: bool = False
    ) -> dict[str, Any]:
        """Stimmen bereits bekannter Polls gezielt und vollständig nachladen."""
        ordered = sorted(set(poll_ids))
        if not ordered or len(ordered) != len(poll_ids):
            raise ValueError("Poll-IDs müssen eindeutig und nicht leer sein.")
        stats: dict[str, Any] = {
            "period_id": period_id,
            "with_votes": True,
            "votes_only": True,
            "poll_ids": ordered,
            "polls": len(ordered),
            "votes": 0,
            "vote_polls_complete": 0,
        }
        run_id = self.database.start_import(
            period_id,
            {"poll_ids": ordered, "votes_only": True, "refresh_mandates": refresh_mandates},
        )
        try:
            period = self._single("parliament-periods", period_id)
            if period.get("type") != "legislature":
                raise APIError("import_votes benötigt eine Legislatur-ID.")
            if refresh_mandates:

                def validate_mandate(item: dict[str, Any]) -> None:
                    require_reference(item, "parliament_period", period_id)
                    if item.get("type") != "mandate":
                        raise APIError("Kandidatur statt Mandat erhalten.")

                refreshed_mandates, _ = self._collection(
                    "candidacies-mandates",
                    {"parliament_period": period_id, "type": "mandate", "current_on": "all"},
                    validate_mandate,
                )
                stats["mandates"] = len(refreshed_mandates)
            mandates = []
            for row in self.database.connection.execute(
                "SELECT payload FROM entities WHERE resource='candidacies-mandates'"
            ):
                mandate = json.loads(row["payload"])
                if (mandate.get("parliament_period") or {}).get("id") == period_id:
                    mandates.append(mandate)
            if not mandates:
                raise APIError("Keine lokalen Mandate; zuerst sync-period ausführen.")
            mandate_ids = {item["id"] for item in mandates}
            polls = []
            for poll_id in ordered:
                row = self.database.connection.execute(
                    "SELECT payload FROM entities WHERE resource='polls' AND entity_id=?",
                    (poll_id,),
                ).fetchone()
                if row is None:
                    raise APIError(
                        f"Poll {poll_id} ist nicht lokal vorhanden; "
                        "zuerst Poll-Metadaten importieren."
                    )
                poll = json.loads(row["payload"])
                require_reference(poll, "field_legislature", period_id)
                polls.append(poll)
            for poll in polls:
                self._import_poll_votes(poll, mandate_ids, stats)
        except (Exception, KeyboardInterrupt) as exc:
            self.database.finish_import(run_id, stats, str(exc) or type(exc).__name__)
            raise
        self.database.finish_import(run_id, stats)
        return {"run_id": run_id, **stats}

    def _programs(self, period: dict[str, Any]) -> int:
        previous = period.get("previous_period")
        if not isinstance(previous, dict) or not isinstance(previous.get("id"), int):
            return 0
        election = self._single("parliament-periods", previous["id"])
        if election.get("type") != "election":
            return 0
        parliament_id = (period.get("parliament") or {}).get("id")
        if parliament_id is None:
            raise APIError("Legislatur ohne Parlament; Wahlzuordnung nicht prüfbar.")
        require_reference(election, "parliament", parliament_id)
        programs, _ = self._collection(
            "election-program",
            {"parliament_period": election["id"]},
            lambda item: require_reference(item, "parliament_period", election["id"]),
        )
        return len(programs)
