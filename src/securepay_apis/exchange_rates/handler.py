"""AWS Lambda entry point: today's rates into DynamoDB.

EventBridge Scheduler calls it once a day, after Frankfurter publishes
(around 16:00 Central European Time). If the API fails or returns invalid
data, fetch() raises, nothing is written and the Lambda ends with an
error, so EventBridge retries it. The engine keeps using the last day it
has meanwhile.
"""

import logging

from securepay_apis.exchange_rates import frankfurter, store

logger = logging.getLogger()
logger.setLevel(logging.INFO)


def handler(event, context):
    result = frankfurter.fetch()
    store.save([result])
    logger.info("Saved rates of %s: %s", result["date"], result["rates"])
    return {"date": result["date"]}
