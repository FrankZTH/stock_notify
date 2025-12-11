# test_startup.py
import time
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# 模擬 Bot 運行，持續運行 60 秒
logging.info("--- TEST SCRIPT STARTING ---")

for i in range(60):
    logging.info(f"Test running... Time elapsed: {i+1} seconds.")
    time.sleep(1)

logging.info("--- TEST SCRIPT FINISHED ---")