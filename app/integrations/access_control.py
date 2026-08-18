import logging
import time


class SimulatedAccessController:
    def open_entry(self, locker_id):
        time.sleep(0.25)
        logging.getLogger(__name__).info(
            "SIMULATED entry gate opened; locker=%s", locker_id
        )

    def open_exit(self):
        time.sleep(0.25)
        logging.getLogger(__name__).info("SIMULATED exit gate opened")

