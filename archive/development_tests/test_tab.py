from app.scraper import get_race_prices


RACE_URL = (
    "https://www.tab.com.au/racing/"
    "2026-08-04/MANDURAH/MRD/G/8"
)


runners = get_race_prices(RACE_URL)

for runner in runners:
    print(
        f"{runner['runner_number']}. "
        f"{runner['runner_name']} | "
        f"Current Price: {runner['current_price']}"
    )