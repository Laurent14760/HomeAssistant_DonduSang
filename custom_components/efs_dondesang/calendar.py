"""Calendrier : un événement par créneau de collecte."""
from __future__ import annotations

from datetime import datetime

from homeassistant.components.calendar import CalendarEntity, CalendarEvent
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.util import dt as dt_util

from . import EfsConfigEntry
from .const import EFS_WEBSITE
from .entity import EfsEntity
from .parser import Collecte, Creneau


async def async_setup_entry(
    hass: HomeAssistant, entry: EfsConfigEntry, async_add_entities: AddEntitiesCallback
) -> None:
    async_add_entities([EfsCalendar(entry.runtime_data)])


def _event(c: Collecte, cr: Creneau) -> CalendarEvent:
    lignes = [
        c.texte_places,
        f"Créneau : {cr.libelle.lower()} ({cr.debut:%Hh%M}-{cr.fin:%Hh%M})",
        f"Distance : {c.distance_km} km",
    ]
    if c.libelle_court:
        lignes.append(c.libelle_court)
    lignes.append(f"Prendre RDV : {c.lien_rdv}" if c.lien_rdv else f"Informations : {EFS_WEBSITE}")
    location = ", ".join(p for p in (c.lieu, c.adresse) if p)
    return CalendarEvent(
        start=cr.debut,
        end=cr.fin,
        summary=f"Don du sang – {c.commune or c.lieu}",
        description="\n".join(lignes),
        location=location,
        uid=f"efs-{c.jour.isoformat()}-{cr.libelle}-{c.lieu}".replace(" ", "_"),
    )


class EfsCalendar(EfsEntity, CalendarEntity):
    _attr_icon = "mdi:calendar-heart"

    def __init__(self, coordinator) -> None:
        super().__init__(coordinator, "collectes", "calendar")

    def _events(self) -> list[CalendarEvent]:
        events = [_event(c, cr) for c in self.collectes for cr in c.creneaux]
        return sorted(events, key=lambda e: e.start)

    @property
    def event(self) -> CalendarEvent | None:
        now = dt_util.now()
        return next((e for e in self._events() if e.end > now), None)

    async def async_get_events(
        self, hass: HomeAssistant, start_date: datetime, end_date: datetime
    ) -> list[CalendarEvent]:
        return [e for e in self._events() if e.end > start_date and e.start < end_date]
