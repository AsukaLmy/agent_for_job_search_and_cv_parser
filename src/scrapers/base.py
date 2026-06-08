"""Base scraper interface."""
import time
from abc import ABC, abstractmethod


class BaseScraper(ABC):
    def __init__(self, delay: float = 2.0):
        self.delay = delay

    def _sleep(self) -> None:
        time.sleep(self.delay)

    @abstractmethod
    def scrape(self, keywords: list[str], **kwargs) -> int:
        """Scrape jobs and upsert into DB. Returns count of new jobs added."""
        ...
