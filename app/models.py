from dataclasses import dataclass


@dataclass
class Runner:
    runner_id: str
    meeting_date: str
    meeting_name: str
    venue_code: str
    race_number: int
    race_start: str
    runner_number: int
    runner_name: str
    initial_price: float
    current_price: float