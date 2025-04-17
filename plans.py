# Plans configuration

PLANS = {
    'basic': {
        'name': 'Plan Básico',
        'price': 'Gratis',
        'daily_searches': 3,
        'daily_requests': 1,
        'can_forward': False,
        'duration_days': None  # No expiration
    },
    'pro': {
        'name': 'Plan Pro',
        'price': '169.99 CUP / 0.49 USD',
        'daily_searches': 15,
        'daily_requests': 2,
        'can_forward': False,
        'duration_days': 30
    },
    'plus': {
        'name': 'Plan Plus',
        'price': '649.99 CUP / 1.99 USD',
        'daily_searches': 50,
        'daily_requests': 10,
        'can_forward': True,
        'duration_days': 30
    },
    'ultra': {
        'name': 'Plan Ultra',
        'price': '1049.99 CUP / 2.99 USD',
        'daily_searches': float('inf'),  # Unlimited
        'daily_requests': float('inf'),  # Unlimited
        'can_forward': True,
        'duration_days': 30
    }
}
