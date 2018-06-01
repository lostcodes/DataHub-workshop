import datetime
import random
import time
import logging
import logging.handlers
from secrets import *
from requests.exceptions import ConnectionError
from twython import Twython, TwythonStreamer, TwythonError, TwythonStreamError
import nltk
from nltk.sentiment.vader import SentimentIntensityAnalyzer
from elasticsearch_dsl.connections import connections
from elasticsearch_dsl import Mapping, GeoPoint, Date


LOGGER = logging.getLogger('Tweet_indexer')
LOGGER.setLevel(logging.DEBUG)
# rotating file handler
FH = logging.handlers.RotatingFileHandler('tweet_logger.log', maxBytes=10000000, backupCount=1)
FH.setLevel(logging.INFO)
# console handler
CH = logging.StreamHandler()
CH.setLevel(logging.INFO)
# add the handlers to the logger
LOGGER.addHandler(FH)
LOGGER.addHandler(CH)

# ES_SERVER = 'http://localhost:9200'
TARGET_INDEX = 'twitter'
DOC_TYPE = 'tweet'


class TweetStreamer(TwythonStreamer):
    es = connections.create_connection(hosts=['localhost'])

    def on_success(self, data):
        LOGGER.info(data)
        # Handle location
        if 'place' in data and data['place'] is not None:
            bb_coordinates = data['place']['bounding_box']['coordinates'][0]
            centroid = evaluate_centroid(bb_coordinates)
            data['centroid'] = centroid

        # Sentiment analysis
        text = data['text'].lower() if data['truncated'] is False else data['extended_tweet']['full_text'].lower()
        sia = SentimentIntensityAnalyzer()
        scores = sia.polarity_scores(text)
        data['sentiment'] = scores['compound']

        # Indexing
        self.es.index(index=TARGET_INDEX, doc_type=DOC_TYPE, body=data)

    def on_error(self, status_code, data):
        LOGGER.error(status_code)

    def on_timeout(self):
        LOGGER.error('The streaming API went timeout!!')


def evaluate_centroid(bb_coordinates):
    sw_point = bb_coordinates[0]
    ne_point = bb_coordinates[2]
    centroid_lat = (sw_point[0] + ne_point[0]) / 2
    centroid_lon = (sw_point[1] + ne_point[1]) / 2
    return [centroid_lat, centroid_lon]


def main():
    nltk.download('vader_lexicon')

    # Prepare ES mappings
    mapping = Mapping('tweet')
    mapping.field('centroid', GeoPoint())
    mapping.field('timestamp_ms', Date())
    mapping.save('twitter')

    try:
        twitter_api = Twython(CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)
        streaming_api = TweetStreamer(CONSUMER_KEY, CONSUMER_SECRET, ACCESS_TOKEN, ACCESS_TOKEN_SECRET)

        # Select bounding box here: http://boundingbox.klokantech.com
        mk_ltn_nham = '-1.0282,51.8575,-0.3249,52.2864' # Milton Keynes + Luton + N'hampton
        us_can = '-126.95,24.7,-59.68,50.01' # US + Canada
        eu_nafr = '-30.2,26.5,52.9,71.0' # Europe + north africa
        streaming_api.statuses.filter(locations=us_can)
    except ConnectionError as err:
        LOGGER.error('Connection error: %s', err)


if __name__ == '__main__':
    main()
