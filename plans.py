from dataclasses import dataclass
from typing import Dict

@dataclass
class Plan:
    name: str
    price: int
    duration_days: int
    daily_searches: int
    can_forward: bool
    description: str

PLANS: Dict[str, Plan] = {
    'free': Plan(
        name='Gratuito',
        price=0,
        duration_days=0,
        daily_searches=3,
        can_forward=False,
        description="Plan gratuito - 3 búsquedas diarias"
    ),
    'standard': Plan(
        name='Estándar',
        price=100,
        duration_days=30,
        daily_searches=20,
        can_forward=True,
        description="Plan Estándar - 20 búsquedas diarias, reenvío permitido"
    ),
    'medium': Plan(
        name='Medio',
        price=150,
        duration_days=30,
        daily_searches=40,
        can_forward=True,
        description="Plan Medio - 40 búsquedas diarias, reenvío permitido"
    ),
    'pro': Plan(
        name='Pro',
        price=200,
        duration_days=30,
        daily_searches=60,
        can_forward=True,
        description="Plan Pro - 60 búsquedas diarias, reenvío permitido"
    )
}