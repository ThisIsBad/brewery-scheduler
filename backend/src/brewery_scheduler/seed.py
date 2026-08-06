"""Seed the database with the real tank inventory from ROADMAP.md §2.2.

Volumes are in hectoliters (1 hl = 100 l). Recipe durations are placeholders
flagged TBD in ROADMAP.md §2.7 — they MUST be confirmed with the brewmaster
before Phase 2 validation logic depends on them.
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from .db import SessionLocal
from .models import (
    Location,
    Recipe,
    Sud,
    SudStatus,
    Tank,
    TankOccupancy,
    TankStage,
)
from .sudplan_import import import_sudplan

# Vincenz' echte Tankwelt (Stefan, 2026-08-06). Namenskonvention: Gär- und
# Lagertanks tragen Rufnamen, Ausschanktanks heißen nach ihrem Keller —
# Typ und Größe kommen aus den Stammdaten, nicht aus dem Namen.
LOCATIONS: list[str] = [
    "Schänke 4",
    "Kitzmann Keller",
    "Resenscheck Keller",
    "Striezi Keller",
    # Historisch (bis 2025) — nur noch für die alten Belegungen.
    "Entlas Keller",
]

TANKS: list[dict] = [
    # Schänke 4 — Gärtanks
    {"name": "Lisa", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "Wanda", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "Greta", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "Anouk", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "Yuri", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 30},
    {"name": "Alva", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 15},
    {"name": "Lovis", "location": "Schänke 4", "stage": TankStage.FERMENTATION_CLOSED, "capacity_hl": 15},
    {"name": "Offener Gärbottich", "location": "Schänke 4", "stage": TankStage.FERMENTATION_OPEN, "capacity_hl": 15},
    # Schänke 4 — Lagertanks
    {"name": "Vincenz", "location": "Schänke 4", "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "Xaver", "location": "Schänke 4", "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "Benjamin", "location": "Schänke 4", "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "Evelyn", "location": "Schänke 4", "stage": TankStage.STORAGE, "capacity_hl": 30},
    {"name": "Fritz", "location": "Schänke 4", "stage": TankStage.STORAGE, "capacity_hl": 30},
    # Schänke 4 — Bergtanks (Ausschank)
    {"name": "Bergtank 120 hl", "location": "Schänke 4", "stage": TankStage.AUSSCHANK, "capacity_hl": 120},
    {"name": "Bergtank 100 hl", "location": "Schänke 4", "stage": TankStage.AUSSCHANK, "capacity_hl": 100},
    # Kitzmann Keller
    {"name": "Kitzmann hinten", "location": "Kitzmann Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 80},
    # Biergartensaison: Ø 15 hl Kellerbier/Woche aus diesem Tank
    # (Stefan, 2026-08-06) — treibt die Reichweiten-Prognose.
    {"name": "Kitzmann vorne", "location": "Kitzmann Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 50, "verbrauch_hl_pro_woche": 15},
    # Resenscheck Keller — nur zur Bergkirchweih im Einsatz
    {"name": "Resenscheck", "location": "Resenscheck Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 80},
    # Entlas Keller — bis 2025 im Ausschank, heute nicht mehr im Betrieb;
    # inaktiv, damit die Historie im Zeitplan weiter rendert.
    {"name": "Entlas", "location": "Entlas Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 100, "active": False},
    # Striezi Keller
    {"name": "Striezi Keller 1", "location": "Striezi Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 35},
    {"name": "Striezi Keller 2", "location": "Striezi Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 35},
    {"name": "Striezi Keller 3", "location": "Striezi Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 10},
    {"name": "Striezi Keller 4", "location": "Striezi Keller", "stage": TankStage.AUSSCHANK, "capacity_hl": 10},
]

# The brewery's real beers, transcribed from Stefans Bierrezepte.xlsx
# (2026-08-04). Quantities are per Sud as written on the sheets. The
# fermentation/storage durations are NOT in the Excel — they are
# placeholders (TBD per ROADMAP.md §2.7) and must be confirmed with the
# brewmaster; same for the Weizenbock open-fermentation assumption.
_ZEITEN_NOTE = (
    "Aus Bierrezepte.xlsx übernommen (2026-08-04); "
    "Gär-/Lagerzeiten sind Platzhalter."
)

RECIPES: list[dict] = [
    {
        "beer_style": "Kellerbier Hell",
        "farbe": "#e0a92e",
        "name": "Brudi",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "original_gravity_plato": 11.9,
        "kochzeit_min": 60,
        "yeast": "Hauptgärung 3470",
        "anstellhinweis": "bei 9,5 Grad anstellen",
        "ingredients": {"malts": [{"name": "Pilsner", "kg": 275, "maelzerei": "BM"}]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 61.5, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 62.5, "dauer_min": 45},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Hallertauer Tradition", "gramm": 616, "alpha_prozent": 6.5, "zeitpunkt": "nach 15 min"},
            {"name": "Perle", "gramm": 414, "alpha_prozent": 9.5, "zeitpunkt": "nach 20 min"},
            {"name": "Citra", "gramm": 50, "alpha_prozent": 13.3, "zeitpunkt": "10 min vor Ende"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        # Zwei unterschiedliche Biere mit gleichem Basisrezept — Sven wird
        # zusätzlich kalt nachgehopft (Stefan, 2026-08-05). Eigene Sorte:
        # ein Rezeptstrang je Sorte, und sortenrein bleibt ehrlich (das
        # kalt gehopfte Bier wird nicht mit Brudi verschnitten).
        "beer_style": "Kellerbier Hell Sven",
        "farbe": "#e5c04a",
        "name": "Sven",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "original_gravity_plato": 11.9,
        "kochzeit_min": 60,
        "yeast": "Hauptgärung 3470",
        "anstellhinweis": "bei 9,5 Grad anstellen",
        "ingredients": {"malts": [{"name": "Pilsner", "kg": 275, "maelzerei": "BM"}]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 61.5, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 62.5, "dauer_min": 45},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Hallertauer Tradition", "gramm": 616, "alpha_prozent": 6.5, "zeitpunkt": "nach 15 min"},
            {"name": "Perle", "gramm": 414, "alpha_prozent": 9.5, "zeitpunkt": "nach 20 min"},
            {"name": "Citra", "gramm": 1550, "alpha_prozent": 13.3, "zeitpunkt": "Kalthopfung"},
        ]},
        "notes": _ZEITEN_NOTE + " Hopfenmengen aus 2026_Sudplanung.xlsx (Blatt Biersorten).",
    },
    {
        "beer_style": "Weizen",
        "farbe": "#d98e2b",
        "name": "Fritz",
        "fermentation_duration_days": 7,
        "open_fermentation_required": True,
        "open_fermentation_duration_days": 4,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
        "original_gravity_plato": 12.5,
        "kochzeit_min": 60,
        "yeast": "Hefe Ingolstadt",
        "ingredients": {"malts": [
            {"name": "Weizen", "kg": 175, "maelzerei": "Weyermann"},
            {"name": "Pilsner", "kg": 58, "maelzerei": "BM"},
            {"name": "Wiener", "kg": 58, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 55, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 63, "dauer_min": 40},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 15},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Fantasia", "gramm": 750, "alpha_prozent": 7.4, "zeitpunkt": "nach 10 min"},
            {"name": "Fantasia", "gramm": 250, "alpha_prozent": 7.4, "zeitpunkt": "nach 50 min"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "Festbier",
        "farbe": "#b06c1a",
        "name": "Gisela",
        "fermentation_duration_days": 8,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 28,
        "max_storage_duration_days": 70,
        "original_gravity_plato": 13.5,
        "ibu": 25.3,
        "kochzeit_min": 70,
        "karbonisierung_g_l": 4.5,
        "yeast": "3470 Wagner",
        "anstellhinweis": "bei 9 Grad anstellen",
        "ingredients": {"malts": [
            {"name": "Pilsner", "kg": 230, "maelzerei": "BM"},
            {"name": "Melanoidinmalz", "kg": 10, "maelzerei": "Weyermann"},
            {"name": "Münchner Typ 2", "kg": 25, "maelzerei": "Weyermann"},
            {"name": "Cara Hell", "kg": 10, "maelzerei": "Weyermann"},
            {"name": "Sauermalz", "kg": 10, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 54, "dauer_min": 5},
            {"schritt": "Rast", "temp_c": 63, "dauer_min": 35},
            {"schritt": "Rast (Vollmundigkeit)", "temp_c": 67, "dauer_min": 15},
            {"schritt": "Rast", "temp_c": 73, "dauer_min": 25},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 15},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Tradition", "gramm": 1514, "alpha_prozent": 6.5, "zeitpunkt": "Kochbeginn"},
            {"name": "Spalter Select", "gramm": 245, "alpha_prozent": 6.7, "zeitpunkt": "nach 35 min"},
            {"name": "Spalter Select", "gramm": 245, "alpha_prozent": 6.7, "zeitpunkt": "nach 55 min"},
            {"name": "Citra", "gramm": 336, "alpha_prozent": 13.2, "zeitpunkt": "Whirlpool"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "Spezialsud",
        "farbe": "#8e5ba6",
        "name": "Schwesti",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "original_gravity_plato": 12.2,
        "kochzeit_min": 60,
        "yeast": "3470 Wagner",
        "ingredients": {"malts": [
            {"name": "Pilsner", "kg": 250, "maelzerei": "BM"},
            {"name": "Cara Pils", "kg": 25, "maelzerei": "Weyermann"},
            {"name": "Münchner Typ 1", "kg": 11, "maelzerei": "Weyermann"},
            {"name": "Sauermalz", "kg": 2, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 61.5, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 62.5, "dauer_min": 45},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Hallertauer Tradition", "gramm": 690, "alpha_prozent": 6.5, "zeitpunkt": "Kochbeginn"},
            {"name": "Spalter Select", "gramm": 900, "alpha_prozent": 6.7, "zeitpunkt": "nach 55 min"},
            {"name": "Hallertauer Mittelfrüh", "gramm": 750, "alpha_prozent": 6, "zeitpunkt": "nach 55 min"},
            {"name": "Citra", "gramm": 1500, "zeitpunkt": "Kalt Gun"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "bay. Dunkel",
        "farbe": "#6b4226",
        "name": "Enno",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "original_gravity_plato": 12.4,
        "kochzeit_min": 70,
        "yeast": "Hauptgärung 3470",
        "anstellhinweis": "bei 9 Grad anstellen",
        "ingredients": {"malts": [
            {"name": "Münchner Malz", "kg": 240, "maelzerei": "BM"},
            {"name": "Cara Hell", "kg": 10, "maelzerei": "Weyermann"},
            {"name": "Münchner Typ 1", "kg": 25, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 55, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 63, "dauer_min": 25},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 30},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Hallertauer Mittelfrüh", "gramm": 400, "zeitpunkt": "Vorderwürze"},
            {"name": "Spalter Select", "gramm": 400, "zeitpunkt": "Vorderwürze"},
            {"name": "Hallertauer Mittelfrüh", "gramm": 600, "zeitpunkt": "10 min nach Kochbeginn"},
            {"name": "Spalter Select", "gramm": 600, "zeitpunkt": "Whirlpool"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "Rauchbier",
        "farbe": "#4a2f1d",
        "name": "Waltraut",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "original_gravity_plato": 12.5,
        "ibu": 23,
        "kochzeit_min": 75,
        "yeast": "3470 Wagner",
        "ingredients": {"malts": [
            {"name": "Wiener", "kg": 150, "maelzerei": "Weyermann"},
            {"name": "Münchner Typ 2", "kg": 60, "maelzerei": "Weyermann"},
            {"name": "Rauchmalz", "kg": 25, "maelzerei": "Weyermann"},
            {"name": "Cara Hell", "kg": 25, "maelzerei": "Weyermann"},
            {"name": "Melanoidin", "kg": 15, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 14, "nachguss_hl": [5]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 57, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 62, "dauer_min": 30},
            {"schritt": "Rast", "temp_c": 73, "dauer_min": 30},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Hallertauer Mittelfrüh", "gramm": 900, "alpha_prozent": 6, "zeitpunkt": "Kochbeginn"},
            {"name": "Spalter Select", "gramm": 1500, "alpha_prozent": 6.7, "zeitpunkt": "nach 55 min"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "Weizenbock",
        "farbe": "#a05c17",
        "name": "Justus",
        "fermentation_duration_days": 7,
        # Wheat-family assumption — offene Gärung wie beim Weizen; vom
        # Braumeister zu bestätigen.
        "open_fermentation_required": True,
        "open_fermentation_duration_days": 4,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "original_gravity_plato": 16,
        "kochzeit_min": 60,
        "yeast": "Hefe Ingolstadt",
        "anstellhinweis": "bei 16 anstellen, auf 20 Grad kommen lassen",
        "ingredients": {"malts": [
            {"name": "Weizen", "kg": 275, "maelzerei": "Weyermann"},
            {"name": "Pilsner", "kg": 75, "maelzerei": "Bamberger"},
            {"name": "Münchner Typ 1", "kg": 25, "maelzerei": "Weyermann"},
            {"name": "Wiener", "kg": 50, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 55, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 63, "dauer_min": 40},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Fantasia", "gramm": 1000, "alpha_prozent": 7.4, "zeitpunkt": "nach 10 min"},
            {"name": "Fantasia", "gramm": 330, "alpha_prozent": 7.4, "zeitpunkt": "10 min vor Ende"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "Collab Widder",
        "farbe": "#2e8b8b",
        "name": "Widder",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
        "original_gravity_plato": 13,
        "kochzeit_min": 60,
        "yeast": "Fermentis S33",
        "anstellhinweis": "bei 18 anstellen, auf 20 Grad kommen lassen",
        "ingredients": {"malts": [
            {"name": "Pale Ale Malz", "kg": 215, "maelzerei": "BM"},
            {"name": "Hafermalz", "kg": 48, "maelzerei": "Steinbach"},
            {"name": "Weizenmalz", "kg": 24, "maelzerei": "Weyermann"},
            {"name": "Cara Pils", "kg": 16, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 64, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 67, "dauer_min": 60},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Cascade", "gramm": 700, "zeitpunkt": "Whirlpool"},
            {"name": "Solero", "gramm": 500, "zeitpunkt": "Whirlpool"},
            {"name": "Bavaria", "gramm": 400, "zeitpunkt": "Kalthopfung 2 Tage nach Gärbeginn"},
            {"name": "Lilly", "gramm": 400, "zeitpunkt": "Kalthopfung 2 Tage nach Gärbeginn"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
    {
        "beer_style": "Wit",
        "farbe": "#cfc06a",
        "name": "Collab Orca",
        "active": False,
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
        "original_gravity_plato": 10,
        "kochzeit_min": 60,
        "yeast": "750 g Trockenhefe belgische Wit",
        "ingredients": {"malts": [
            {"name": "Weizen", "kg": 45, "maelzerei": "Weyermann"},
            {"name": "Pilsner", "kg": 115, "maelzerei": "BM"},
            {"name": "Weizenrohfrucht", "kg": 75},
            {"name": "Reishülsen", "kg": 3},
        ]},
        "wasser": {"hauptguss_hl": 9.5, "nachguss_hl": [6.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 52, "dauer_min": 40},
            {"schritt": "Rast", "temp_c": 63, "dauer_min": 35},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 30},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 15},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Perle", "gramm": 900, "zeitpunkt": "nach 1 min"},
            {"name": "Fantasia", "gramm": 1000, "zeitpunkt": "Whirlpool 10 min"},
        ]},
        "notes": _ZEITEN_NOTE + " Orangenschalen ca. 3 h zirkuliert.",
    },
    {
        # Frühere Biere aus der 2021-2024-Historie — Rezeptdaten unbekannt,
        # archiviert; nur damit die alten Sude eine Heimat haben.
        "beer_style": "Keller Bern",
        "farbe": "#9c7a3c",
        "name": "Keller Bern",
        "active": False,
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 21,
        "max_storage_duration_days": 60,
        "notes": "Aus der Sudhistorie 2021-2024 angelegt — Rezept unbekannt.",
    },
    {
        "beer_style": "Bock",
        "farbe": "#7a4a21",
        "name": "Bock",
        "active": False,
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 28,
        "max_storage_duration_days": 90,
        "notes": "Aus der Sudhistorie 2021 angelegt — Rezept unbekannt.",
    },
    {
        "beer_style": "Collab Sud 2025",
        "farbe": "#4a8b6f",
        "name": "Collab 2025",
        "active": False,
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
        "notes": "Aus der Sudplanung 2025 angelegt — Partner und Rezept offen.",
    },
    {
        # Aus der Sudplanung 2026 (Sud 265) — im Excel ohne Rezeptdaten;
        # Zutaten und Zeiten trägt Vincenz nach.
        "beer_style": "Wiener Lager",
        "farbe": "#b3541e",
        "name": "Leopold",
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
        "kochzeit_min": 60,
        "notes": "Aus 2026_Sudplanung.xlsx angelegt — Zutaten/Zeiten offen.",
    },
    {
        "beer_style": "Leichtbier",
        "farbe": "#c0392b",
        "name": "Werner",
        "active": False,
        "fermentation_duration_days": 7,
        "open_fermentation_required": False,
        "open_fermentation_duration_days": None,
        "storage_duration_days": 14,
        "max_storage_duration_days": 45,
        "kochzeit_min": 60,
        "yeast": "Hauptgärung 3470",
        "ingredients": {"malts": [
            {"name": "Pilsner", "kg": 100, "maelzerei": "BM"},
            {"name": "Cara Red", "kg": 25, "maelzerei": "Weyermann"},
            {"name": "Münchner Typ 1", "kg": 45, "maelzerei": "Weyermann"},
            {"name": "Melanoidin", "kg": 15, "maelzerei": "Weyermann"},
        ]},
        "wasser": {"hauptguss_hl": 11, "nachguss_hl": [5.5, 3]},
        "mash_schedule": {"rasten": [
            {"schritt": "Einmaischen", "temp_c": 58, "dauer_min": 10},
            {"schritt": "Rast", "temp_c": 62.5, "dauer_min": 45},
            {"schritt": "Rast", "temp_c": 72, "dauer_min": 20},
            {"schritt": "Abmaischen", "temp_c": 78, "dauer_min": 10},
        ]},
        "hop_additions": {"gaben": [
            {"name": "Perle", "gramm": 400, "alpha_prozent": 6.5, "zeitpunkt": "nach 15 min"},
            {"name": "Perle", "gramm": 100, "alpha_prozent": 9.5, "zeitpunkt": "nach 20 min"},
            {"name": "Perle", "gramm": 160, "zeitpunkt": "Whirlpool"},
        ]},
        "notes": _ZEITEN_NOTE,
    },
]


def seed(
    session: Session, *, demo_sude: bool = False, sudplan: bool = True
) -> None:
    """Grunddaten (Standorte, Tanks, Rezepte) plus wahlweise Sude.

    sudplan: Vincenz' echte Sudplanung 2026 — der Standard für Dev und
    Prod, damit der Umstieg vom Excel nahtlos ist.
    demo_sude: die kleine, vorhersagbare Vier-Sude-Welt, auf der die
    Test-Suite aufbaut (conftest ruft seed mit demo_sude=True, sudplan=False).
    """
    if session.scalar(select(Tank).limit(1)) is not None:
        print("Database already seeded — skipping.")
        return

    # Locations may already exist (created by migration 0008 on a database
    # that predates them); reuse instead of duplicating.
    locations = {loc.name: loc for loc in session.scalars(select(Location))}
    for position, name in enumerate(LOCATIONS, start=1):
        if name not in locations:
            location = Location(name=name, position=position)
            session.add(location)
            locations[name] = location
    session.flush()

    tanks = [
        Tank(
            name=t["name"],
            location_id=locations[t["location"]].id,
            stage=t["stage"],
            capacity_hl=t["capacity_hl"],
            active=t.get("active", True),
            verbrauch_hl_pro_woche=t.get("verbrauch_hl_pro_woche"),
        )
        for t in TANKS
    ]
    session.add_all(tanks)

    recipes = [Recipe(**r) for r in RECIPES]
    session.add_all(recipes)
    session.flush()

    if sudplan:
        stats = import_sudplan(session)
        session.commit()
        print(
            f"Seeded: {len(tanks)} tanks, {len(recipes)} recipes, "
            f"Sudplan 2026: {stats['sude']} Sude ({stats['paare']} Doppelsude), "
            f"{stats['belegungen']} Belegungen, {stats['verworfen']} Kollisionen, "
            f"{stats['hinweise']} Hinweise."
        )

    if not demo_sude:
        if not sudplan:
            session.commit()
            print(f"Seeded: {len(tanks)} tanks, {len(recipes)} recipes, keine Sude.")
        return

    # Zwei Rezepte teilen sich die Sorte "Kellerbier Hell" — für die Demo-Welt
    # zählt der Name, nicht die Sorte.
    by_name = {r.name: r for r in recipes}
    by_style = {
        "Kellerbier Hell": by_name["Brudi"],
        "Weizen": by_name["Fritz"],
        "Festbier": by_name["Gisela"],
    }
    by_tank = {t.name: t for t in tanks}

    today = date.today()
    midnight_utc = datetime.combine(today, datetime.min.time(), tzinfo=timezone.utc)

    # Past brew dates are clamped into the current year: early in January,
    # "today - 14 days" would land in the previous year, silently shifting
    # which (style, year) bucket the seeded Sude occupy and breaking every
    # test that assumes they are the first of the current year.
    def past_brew_date(days_ago: int) -> date:
        return max(date(today.year, 1, 1), today - timedelta(days=days_ago))

    def brew_morning(d: date) -> datetime:
        return datetime.combine(d, time(8), tzinfo=timezone.utc)

    # Sample plan that exercises the full pipeline so the Gantt isn't empty
    # on first launch. The numbers don't reflect real brewing schedules —
    # they're just plausible enough that the brewmaster can drag them around
    # to get a feel for the UX. style_year_number is 1 for each because each
    # is the first of its style in this brew_date's year. global_number is
    # left to the sud_global_seq default.
    kellerbier_day = past_brew_date(14)
    kellerbier = Sud(
        recipe_id=by_style["Kellerbier Hell"].id,
        beer_style="Kellerbier Hell",
        brew_at=brew_morning(kellerbier_day),
        brew_date=kellerbier_day,
        status=SudStatus.STORING,
        brewmaster="seed",
        style_year_number=1,
    )
    weizen_day = past_brew_date(7)
    weizen = Sud(
        recipe_id=by_style["Weizen"].id,
        beer_style="Weizen",
        brew_at=brew_morning(weizen_day),
        brew_date=weizen_day,
        status=SudStatus.FERMENTING,
        brewmaster="seed",
        style_year_number=1,
    )
    # Future brew dates are clamped so lead AND partner stay inside the
    # current year — around Christmas, "today + 8 days" would cross into
    # January and silently invalidate the hardcoded style_year_numbers.
    def future_brew_date(days_ahead: int) -> date:
        return min(date(today.year, 12, 30), today + timedelta(days=days_ahead))

    festbier_day = future_brew_date(7)
    festbier = Sud(
        recipe_id=by_style["Festbier"].id,
        beer_style="Festbier",
        brew_at=brew_morning(festbier_day),
        brew_date=festbier_day,
        status=SudStatus.PLANNED,
        brewmaster="seed",
        style_year_number=1,
    )
    session.add_all([kellerbier, weizen, festbier])
    session.flush()

    # Merged batch (issue #3): the same Festbier recipe brewed again a day
    # later shares the lead's 30-hl fermentation tank. The partner carries
    # no occupancies of its own.
    festbier_partner = Sud(
        recipe_id=by_style["Festbier"].id,
        beer_style="Festbier",
        brew_at=brew_morning(festbier.brew_date + timedelta(days=1)),
        brew_date=festbier.brew_date + timedelta(days=1),
        status=SudStatus.PLANNED,
        brewmaster="seed",
        style_year_number=2,
        merged_into_sud_id=festbier.id,
    )
    session.add(festbier_partner)
    session.flush()

    occupancies = [
        # Kellerbier: finished fermenting, currently in storage.
        TankOccupancy(
            sud_id=kellerbier.id,
            tank_id=by_tank["Lisa"].id,
            stage=TankStage.FERMENTATION_CLOSED,
            start_at=midnight_utc - timedelta(days=14),
            end_at=midnight_utc - timedelta(days=7),
        ),
        TankOccupancy(
            sud_id=kellerbier.id,
            tank_id=by_tank["Vincenz"].id,
            stage=TankStage.STORAGE,
            start_at=midnight_utc - timedelta(days=7),
            end_at=midnight_utc + timedelta(days=14),
        ),
        # Weizen: open ferm done, now in closed fermentation.
        TankOccupancy(
            sud_id=weizen.id,
            tank_id=by_tank["Offener Gärbottich"].id,
            stage=TankStage.FERMENTATION_OPEN,
            start_at=midnight_utc - timedelta(days=7),
            end_at=midnight_utc - timedelta(days=3),
        ),
        TankOccupancy(
            sud_id=weizen.id,
            tank_id=by_tank["Alva"].id,
            stage=TankStage.FERMENTATION_CLOSED,
            start_at=midnight_utc - timedelta(days=3),
            end_at=midnight_utc + timedelta(days=4),
        ),
        # Festbier: planned ferm + storage in the future.
        TankOccupancy(
            sud_id=festbier.id,
            tank_id=by_tank["Wanda"].id,
            stage=TankStage.FERMENTATION_CLOSED,
            start_at=midnight_utc + timedelta(days=7),
            end_at=midnight_utc + timedelta(days=15),
        ),
        TankOccupancy(
            sud_id=festbier.id,
            tank_id=by_tank["Xaver"].id,
            stage=TankStage.STORAGE,
            start_at=midnight_utc + timedelta(days=15),
            end_at=midnight_utc + timedelta(days=43),
        ),
    ]
    session.add_all(occupancies)

    session.commit()
    sude = [kellerbier, weizen, festbier, festbier_partner]
    print(
        f"Seeded: {len(tanks)} tanks, {len(recipes)} recipes, "
        f"{len(sude)} Sude (incl. 1 merged batch), "
        f"{len(occupancies)} tank occupancies."
    )


def main() -> None:
    with SessionLocal() as session:
        seed(session)


if __name__ == "__main__":
    main()
