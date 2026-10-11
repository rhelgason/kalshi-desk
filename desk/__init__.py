"""
The trading desk: a Kalshi-first engine where each strategy is an "employee".

Layout:
    desk.kalshi      - API client, auth, data models, fee math
    desk.feeds       - outside data (crypto spot prices and volatility)
    desk.strategies  - the employees: each looks at a snapshot and proposes trades
    desk.paper       - paper-trading broker, ledger, and scoreboard
    desk.runner      - the loop that ties it all together
"""
