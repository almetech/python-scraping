# Represents all the Models used to create our scraper

import argparse
import datetime
import glob
import json
import os
import pickle
import re
import sqlite3

import pymysql
from decouple import UndefinedValueError, config
from pytz import timezone
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        MetaData, String, Table, Text, create_engine, exc)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapper, relationship, sessionmaker
from sqlalchemy.orm.exc import FlushError, NoResultFound
from sqlitedict import SqliteDict

import tokenize_titles
from utils import create_logger, subcategory_map

# This is required for integration with MySQL and Python
pymysql.install_as_MySQLdb()

# Create the logger
logger = create_logger(__name__)

productlisting_logger = create_logger('productlisting')
productdetails_logger = create_logger('productdetails')
qanda_logger = create_logger('qanda')
reviews_logger = create_logger('reviews')

# Our Database Schema
tables = {
    'ProductListing': {
        'product_id': 'TEXT(16) PRIMARY KEY',
        'category': 'TEXT(100)',
        'title': 'LONGTEXT',
        'domain': 'TEXT(60)',
        'product_url': 'LONGTEXT',
        'avg_rating': 'FLOAT',
        'total_ratings': 'INTEGER',
        'price': 'FLOAT',
        'old_price': 'FLOAT',
        'secondary_information': 'LONGTEXT',
        'image': 'TEXT(1000)',
        'is_duplicate': 'BOOLEAN',
        'short_title': 'TEXT(100)',
        'duplicate_set': 'INTEGER',
        'is_active': 'BOOLEAN',
        'date_completed': 'DATETIME',
        'brand': 'TEXT(100)',
        'alert': 'BOOLEAN',
        },
    'ProductDetails': {
        'product_id': 'TEXT(16) PRIMARY KEY',
        'product_title': 'LONGTEXT',
        'byline_info': 'LONGTEXT',
        'num_reviews': 'INTEGER',
        'answered_questions': 'TEXT(100)',
        'curr_price': 'FLOAT',
        'features': 'LONGTEXT',
        'offers': 'LONGTEXT',
        'description': 'LONGTEXT',
        'product_details': 'LONGTEXT',
        'featurewise_reviews': 'LONGTEXT',
        'customer_qa': 'LONGTEXT',
        'customer_lazy': 'INTEGER',
        'histogram': 'LONGTEXT',
        'reviews_url': 'LONGTEXT',
        'created_on': 'DATETIME',
        'subcategories': 'LONGTEXT',
        'is_sponsored': 'BOOLEAN',
        'completed': 'BOOLEAN',
        'brand': 'TEXT(100)',
        'model': 'TEXT(100)',
        'date_completed': 'DATETIME',
        'is_duplicate': 'BOOLEAN',
        'alert': 'BOOLEAN',
    },
    'SponsoredProductDetails': {
        'product_id': 'TEXT(16) PRIMARY KEY',
        'product_title': 'LONGTEXT',
        'byline_info': 'LONGTEXT',
        'num_reviews': 'INTEGER',
        'answered_questions': 'TEXT(100)',
        'curr_price': 'FLOAT',
        'features': 'LONGTEXT',
        'offers': 'LONGTEXT',
        'description': 'LONGTEXT',
        'product_details': 'LONGTEXT',
        'featurewise_reviews': 'LONGTEXT',
        'customer_qa': 'LONGTEXT',
        'customer_lazy': 'INTEGER',
        'histogram': 'LONGTEXT',
        'reviews_url': 'LONGTEXT',
        'created_on': 'DATETIME',
        'subcategories': 'LONGTEXT',
        'is_sponsored': 'BOOLEAN',
    },
    'QandA': {
        'id': 'INTEGER PRIMARY KEY',
        'product_id': 'TEXT(16)',
        'question': 'LONGTEXT',
        'answer': 'LONGTEXT',
        'date': 'DATETIME',
        'page_num': 'INTEGER',
        'is_duplicate': 'BOOLEAN',
        'duplicate_set': 'INTEGER',
        '_product_id': ['FOREIGN KEY', 'REFERENCES ProductListing (product_id)'],
    },
    'Reviews': {
        'id': 'INTEGER PRIMARY KEY',
        'product_id': 'TEXT(16)',
        'rating': 'FLOAT',
        'review_date': 'DATETIME',
        'country': 'TEXT(40)',
        'title': 'TEXT(1000)',
        'body': 'LONGTEXT',
        'product_info': 'LONGTEXT',
        'verified_purchase': 'INTEGER',
        'helpful_votes': 'INTEGER',
        'page_num': 'INTEGER',
        'is_duplicate': 'BOOLEAN',
        'duplicate_set': 'INTEGER',
        '_product_id': ['FOREIGN KEY', 'REFERENCES ProductListing (product_id)'],
    },
    'DailyProductListing': {
        'id': 'INTEGER PRIMARY KEY',
        'product_id': 'TEXT(16)',
        'category': 'TEXT(100)',
        'serial_no': 'INTEGER',
        'avg_rating': 'FLOAT',
        'total_ratings': 'INTEGER',
        'price': 'FLOAT',
        'old_price': 'FLOAT',
        'date': 'DATETIME',
        #'_product_id': ['FOREIGN KEY', 'REFERENCES ProductListing (product_id)'],
    },
    'SentimentAnalysis': {
        'id': 'INTEGER PRIMARY KEY',
        'product_id': 'TEXT(16)',
        'review_id': 'INTEGER',
        'sentiments': 'LONGTEXT',
        'duplicate_set': 'INTEGER',
    }
}

field_map = {
    'INTEGER': Integer,
    'TEXT': String,
    'FLOAT': Float,
    'DATETIME': DateTime,
    'BOOLEAN': Boolean,
    'LONGTEXT': Text,
}


class Database():
    db_file = 'db.sqlite'
    DB_ENGINE = {
        'sqlite': f'sqlite:///{db_file}',
    }

    # Main DB Connection Ref Obj
    db_engine = None
    def __init__(self, dbtype='sqlite', username='', password='', port=3306, dbname='', server=''):
        dbtype = dbtype.lower()
        if dbtype in self.DB_ENGINE.keys():
            engine_url = self.DB_ENGINE[dbtype].format(DB=dbname)
            self.db_engine = create_engine(engine_url)
        elif dbtype.startswith('mysql'):
            # mysql+pymysql also supported
            engine_url = f'{dbtype}://{username}:{password}@{server}:{port}/{dbname}'
            self.db_engine = create_engine(engine_url)
            self.db_engine.connect()
            self.db_engine.execute(f"CREATE DATABASE IF NOT EXISTS {dbname}")
            self.db_engine.execute(f"USE {dbname}")
        else:
            raise ValueError("DBType is not found in DB_ENGINE")


# Database Session setup
try:
    DB_USER = config('DB_USER')
    DB_PASSWORD = config('DB_PASSWORD')
    DB_NAME = config('DB_NAME')
    DB_SERVER = config('DB_SERVER')
    DB_TYPE = config('DB_TYPE')
    engine = Database(dbtype=DB_TYPE, username=DB_USER, password=DB_PASSWORD, dbname=DB_NAME, server=DB_SERVER).db_engine
except UndefinedValueError:
    DB_TYPE = 'sqlite'
    engine = Database(dbtype=DB_TYPE).db_engine

# And the metadata
metadata = MetaData(bind=engine)


try:
    DEVELOPMENT = config('DEVELOPMENT', cast=bool)
except:
    DEVELOPMENT = False


def get_credentials():
    from decouple import config

    try:
        connection_params = {
            'dbtype': config('DB_TYPE'),
            'username': config('DB_USER'),
            'password': config('DB_PASSWORD'),
            'server': config('DB_SERVER'),
        }
    except:
        connection_params = None

    return connection_params


def connect_to_db(db_name, connection_params):
    engine = Database(dbname=db_name, **(connection_params)).db_engine
    return engine


def apply_schema(cls):
    # Refer https://stackoverflow.com/a/2575016
    table = tables[cls.__name__]
    columns = []

    _fk_field = {} # Assume one FK per table
    for field in table:
        if isinstance(table[field], list) and 'FOREIGN KEY' in table[field]:
            _fk_field = {'field': field[1:], 'parent': table[field][1].split()[1], 'fk_field': table[field][1].split()[2][1:-1]}

    for field in table:
        is_foreign_key = False

        if 'field' in _fk_field and field == _fk_field['field']:
            is_foreign_key = True
            parent = _fk_field['parent']
            fk_field = _fk_field['fk_field']

        if isinstance(table[field], list) and 'FOREIGN KEY' in table[field]:
            continue

        datatype = table[field].split()[0]
        
        pattern = r'(.+)\ *\(([0-9]+)\)$'
        match = re.match(pattern, datatype)
        
        if match is not None:
            datatype = match.groups()[0]
            size = int(match.groups()[1])
        else:
            size = None

        datatype = field_map[datatype]

        if datatype == String:
            if size is not None:
                datatype = String(size)
            else:
                datatype = String(None)
        elif datatype == Text:
            if size is not None:
                datatype = Text(size)
            else:
                datatype = Text()
        
        args = [field, datatype]
        kwargs = dict()

        if 'PRIMARY KEY' in table[field]:
            kwargs['primary_key'] = True
        if is_foreign_key == True:
            # Set the relationship attribute on the parent class
            relation = relationship(cls.__name__)
            setattr(globals()[parent], cls.__name__.lower(), relation)

            fk_args = [parent + '.' + fk_field]
            fk = ForeignKey(*fk_args)
            args.append(fk)

        column = Column(*args, **kwargs)
        columns.append(column)

    table = Table(cls.__name__, metadata, *(column for column in columns))
    metadata.create_all()
    mapper(cls, table)
    return cls


@apply_schema
class ProductListing():
    pass


@apply_schema
class ProductDetails():
    pass


@apply_schema
class SponsoredProductDetails():
    pass


@apply_schema
class QandA():
    pass


@apply_schema
class Reviews():
    pass


@apply_schema
class DailyProductListing():
    pass


@apply_schema
class SentimentAnalysis():
    pass


table_map = {
    'ProductListing': ProductListing,
    'ProductDetails': ProductDetails,
    'SponsoredProductDetails': SponsoredProductDetails,
    'QandA': QandA,
    'Reviews': Reviews,
    'DailyProductListing': DailyProductListing,
    'SentimentAnalysis': SentimentAnalysis,
}


def get_short_title(product_title):
    if product_title is None:
        return product_title
    
    if product_title.startswith('(Renewed)'):
        product_title = product_title[9:].strip()
    
    return tokenize_titles.remove_stop_words(product_title)


def insert_product_listing(session, data, table='ProductListing', domain='amazon.in'):
    row = dict()
    row['domain'] = domain
    for category in data:
        row['category'] = category
        for page_num in data[category]:
            for title in data[category][page_num]:
                row['title'] = title
                try:
                    row['short_title'] = get_short_title(title)
                except:
                    row['short_title'] = None
                
                if row['short_title'] is None:
                    row['brand'] = None
                else:
                    try:
                        row['brand'] = row['short_title'].split()[0]
                    except:
                        row['brand'] = None
                
                value = data[category][page_num][title]
                for key in value:
                    if value[key] is not None:
                        if key == 'avg_rating':
                            row[key] = float(value[key].split()[0])
                        elif key == 'total_ratings':
                            row[key] = int(value[key].replace(',', '').replace('.', ''))
                        elif key in ('price', 'old_price'):
                            row[key] = float(value[key].replace(',', ''))
                        else:
                            row[key] = value[key]
                    else:
                        row[key] = value[key]
                try:
                    if row['product_id'] is not None:
                        obj = table_map[table]()
                        row['is_duplicate'] = None
                        [setattr(obj, key, value) for key, value in row.items() if hasattr(obj, key)]
                        session.add(obj)
                        session.commit()
                        continue
                except (exc.IntegrityError, FlushError,):
                    session.rollback()
                    result = session.query(table_map[table]).filter(ProductListing.product_id == row['product_id']).first()
                    if result is None:
                        continue
                    else:
                        update_fields = [field for field in tables[table] if field != "product_id"]
                        temp = getattr(result, 'is_duplicate')
                        short_title = getattr(result, 'short_title')
                        for field in update_fields:
                            if field in row:
                                setattr(result, field, row[field])
                        setattr(result, 'is_duplicate', temp)
                        if short_title is not None:
                            setattr(result, 'short_title', short_title)
                        try:
                            session.commit()
                            continue
                        except:
                            session.rollback()
                            logger.warning(f"For Product {row['product_id']}, there is an error with the data.")
                            logger.newline()
                            continue
                except Exception as ex:
                    session.rollback()
                    productlisting_logger.critical(f"{row['product_id']}-> Exception: {ex}")
                    logger.warning(f"For Product {row['product_id']}, there is an error with the data.")
                    logger.newline()
                    continue
    return True


def insert_daily_product_listing(session, data, table='DailyProductListing'):
    row = dict()
    for category in data:
        for page_num in data[category]:
            for title in data[category][page_num]:
                value = data[category][page_num][title]
                for key in value:
                    if value[key] is not None:
                        if key == 'avg_rating':
                            row[key] = float(value[key].split()[0])
                        elif key == 'total_ratings':
                            row[key] = int(value[key].replace(',', '').replace('.', ''))
                        elif key in ('price', 'old_price'):
                            row[key] = float(value[key].replace(',', ''))
                        else:
                            row[key] = value[key]
                    else:
                        row[key] = value[key]
                try:
                    if row['product_id'] is not None:
                        row['date'] = datetime.datetime.now(timezone('Asia/Kolkata'))#.date()
                        row['category'] = category
                        obj = table_map[table]()
                        [setattr(obj, key, value) for key, value in row.items() if hasattr(obj, key)]
                        session.add(obj)
                        session.commit()
                        continue
                except exc.IntegrityError:
                    session.rollback()
                    result = session.query(table_map[table]).filter(ProductListing.product_id == row['product_id']).first()
                    if result is None:
                        pass
                    else:
                        update_fields = [field for field in tables[table] if hasattr(result, field) and getattr(result, field) in (None, {}, [], "", "{}", "[]")]
                        for field in update_fields:
                            if field in row:
                                setattr(result, field, row[field])
                        # Update the date
                        date = datetime.datetime.now(timezone('Asia/Kolkata'))#.date()
                        setattr(result, 'date', date)
                        try:
                            session.commit()
                            continue
                        except:
                            session.rollback()
                            logger.warning(f"For Product {row['product_id']}, there is an error with the data.")
                            logger.newline()
                            continue
                except Exception as ex:
                    session.rollback()
                    productlisting_logger.critical(f"{row['product_id']} -> Exception: {ex}")
                    logger.warning(f"For Product {row['product_id']}, there is an error with the data.")
                    logger.newline()
                    continue
    return True


def insert_product_details(session, data, table='ProductDetails', is_sponsored=False):
    row = {key: (data[key] if not (isinstance(data[key], list) or isinstance(data[key], dict)) else json.dumps(data[key])) for key in data}
    for field in row:
        if row[field] is not None:
            if field == 'num_reviews':
                row[field] = int(row[field].split()[0].replace(',', '').replace('.', ''))
            elif field in ('curr_price'):
                row[field] = float(row[field].replace(',', ''))
    row['created_on'] = datetime.datetime.now()
    row['is_sponsored'] = is_sponsored
    try:
        obj = table_map[table]()
        [setattr(obj, key, value) for key, value in row.items() if hasattr(obj, key)]
        session.add(obj)
        session.commit()
        return True
    except (exc.IntegrityError, FlushError):
        session.rollback()
        result = session.query(table_map[table]).filter(ProductDetails.product_id == row['product_id']).first()
        update_fields = (field for field in tables[table] if hasattr(result, field) and getattr(result, field) in (None, {}, [], "", "{}", "[]"))
        for field in update_fields:
            if field in row:
                setattr(result, field, row[field])
        try:
            session.commit()
            return True
        except Exception as ex:
            session.rollback()
            productdetails_logger.critical(f"{row['product_id']} -> Exception: {ex}")
            logger.warning(f"For Product {row['product_id']}, there is an error with the data.")
            logger.newline()
            return False
    except Exception as ex:
        session.rollback()
        productdetails_logger.critical(f"{row['product_id']} -> Exception: {ex}")
        logger.warning(f"For Product {row['product_id']}, there is an error with the data.")
        logger.newline()
        return False


def insert_product_qanda(session, qanda, product_id, table='QandA', duplicate_set=None):
    for pair in qanda:
        row = {key: (value if not isinstance(value, list) and not isinstance(value, dict) else json.dumps(value)) for key, value in pair.items()}
        # Add product id
        row['product_id'] = product_id
        row['duplicate_set'] = duplicate_set
        row['is_duplicate'] = False
        obj = table_map[table]()
        [setattr(obj, key, val) for key, val in row.items()]
        session.add(obj)
    # TODO: Change this later outisde the loop
    try:
        session.commit()
        return True
    except Exception as ex:
        session.rollback()
        qanda_logger.critical(f"{product_id} -> Exception: {ex}")
        logger.warning(f" For Product {product_id}, there is an error with the data.")
        logger.newline()
        return False


def insert_product_reviews(session, reviews, product_id, table='Reviews', duplicate_set=None):
    for review in reviews['reviews']:
        row = dict()
        # Add product id
        row['product_id'] = product_id
        row['rating'] = float(review['rating'].split()[0])
        row['review_date'] = review['review_date']
        row['country'] = review['country']
        row['title'] = review['title']
        row['body'] = review['body']
        if isinstance(review['product_info'], list) or isinstance(review['product_info'], dict):
            row['product_info'] = json.dumps(review['product_info'])
        else:
            row['product_info'] = json.dumps(review['product_info'])
        row['verified_purchase'] = review['verified_purchase']
        row['helpful_votes'] = review['helpful_votes']
        row['page_num'] = review['page_num']
        row['is_duplicate'] = False
        row['duplicate_set'] = duplicate_set
        obj = table_map[table]()
        [setattr(obj, key, val) for key, val in row.items()]
        session.add(obj)
    # TODO: Change this later outisde the loop
    try:
        session.commit()
        return True
    except Exception as ex:
        session.rollback()
        reviews_logger.critical(f"{product_id} -> Exception: {ex}")
        logger.warning(f"For Product {product_id}, there is an error with the data.")
        logger.newline()
        return False


def query_table(session, table, query='all', filter_cond=None):
    if query == 'all':
        if filter_cond is None:
            try:
                instance = session.query(table_map[table]).all()
                return instance
            except:
                return None
        elif isinstance(filter_cond, list):
            # Filter IN
            filter_type = filter_cond[0]
            assert filter_type in ['in']
            try:
                if filter_type == 'in':
                    assert len(filter_cond) == 3
                    column = filter_cond[1]
                    choices = filter_cond[2]
                    instance = session.query(table_map[table]).filter(getattr(table_map[table], column).in_(choices)).all()
                    return instance
            except:
                return None
        else:
            # Filter Condition MUST be a dict
            assert isinstance(filter_cond, dict)
            try:
                instance = session.query(table_map[table]).filter_by(**filter_cond).all()
                return instance
            except:
                return None
    
    elif query == 'one':
        if filter_cond is None:
            try:
                instance = session.query(table_map[table]).one()
                return instance
            except:
                return None
        else:
            # Filter Condition MUST be a dict
            assert isinstance(filter_cond, dict)
            try:
                instance = session.query(table_map[table]).filter_by(**filter_cond).one()
                return instance
            except:
                return None
    
    else:
        return None


def fetch_product_ids(session, table, categories):
    result = []
    if not isinstance(categories, list):
        categories = [categories]
    for category in categories:
        try:
            instances = session.query(table_map[table]).filter_by(category=category).all()
            result.extend([getattr(instance, 'product_id') for instance in instances])
        except:
            result.extend([])
    return result


def add_column(engine, table_name: str, column: Column):
    column_name = column.compile(dialect=engine.dialect)
    column_type = column.type.compile(engine.dialect)
    engine.execute('ALTER TABLE %s ADD COLUMN %s %s' % (table_name, column_name, column_type))


def alter_column(engine, table_name: str, column_name: str, new_name: str, data_type: str):
    engine.execute('ALTER TABLE %s CHANGE COLUMN %s %s %s' % (table_name, column_name, new_name, data_type))


def dump_listing_from_cache(session, category, cache_file='cache.sqlite3'):
    with SqliteDict(cache_file) as cache:
        today = datetime.datetime.today().strftime("%d-%m-%y")
        for page in range(1, 100):
            key = f"LISTING_{category}_PAGE_{page}_{today}"
            value = cache.get(key)
            if value is None:
                continue
            try:
                status = insert_product_listing(session, value, table='ProductListing')
                if status == False:
                    logger.warning(f"Status = False for category: {category}, page: {page}")
                else:
                    logger.info(f"Category: {category}, Inserted Page: {page}")
            except Exception as ex:
                print(ex)


def dump_from_cache(session, category, cache_file='cache.sqlite3'):
    with SqliteDict(cache_file, autocommit=True) as cache:
        key = f"DETAILS_SET_{category}"
        if key in cache:
            _set = cache[key]
            for product_id in _set:
                logger.info(f"Dumping Product ID {product_id}")
                
                qanda_counter = 0
                reviews_counter = 0

                qanda_errors = f"ERRORS_QANDA_{product_id}"
                reviews_errors = f"ERRORS_REVIEWS_{product_id}"

                if qanda_errors not in cache:
                    cache[qanda_errors] = set()
                
                _q = cache[qanda_errors]
                
                if reviews_errors not in cache:
                    cache[reviews_errors] = set()
                
                _r = cache[reviews_errors]

                for page_num in range(10+1):
                    key = f"QANDA_{product_id}_{page_num}"
                    if key not in cache:
                        continue

                    data = cache[key]

                    if len(data) == 0 or 'page_num' not in data[0]:
                        continue

                    status = insert_product_qanda(session, data, product_id)
                    
                    if status == False:
                        logger.error(f"QandA: Error during dumping PAGE-{page_num} from cache for Product ID {product_id}")
                        _q.add(page_num)
                        break
                    else:
                        qanda_counter += 1
                        del cache[key]
                
                cache[qanda_errors] = _q
                
                for page_num in range(100+1):
                    key = f"REVIEWS_{product_id}_{page_num}"
                    if key not in cache:
                        continue
                    
                    data = cache[key]

                    if len(data) == 0 or 'page_num' not in data['reviews'][0]:
                        continue

                    status = insert_product_reviews(session, data, product_id)

                    if status == False:
                        logger.error(f"Reviews: Error during dumping PAGE - {page_num} from cache for Product ID {product_id}")
                        _r.add(page_num)
                        break
                    else:
                        reviews_counter += 1
                        del cache[key]
                
                cache[reviews_errors] = _r

                logger.info(f"For PRODUCT ID {product_id}, dumped {qanda_counter} QandA pages, and {reviews_counter} Review Pages")


def update_brands_and_models(session, table='ProductDetails'):
    instances = session.query(table_map[table]).all()
    for instance in instances:
        if instance.brand is not None and instance.model is not None:
            continue
        brand = None
        _model = None
        if instance.product_details not in (None, {}, "{}"):
            # Get the brand
            details = json.loads(instance.product_details)
            key = 'Technical Details' if 'Technical Details' in details else 'Product Details'
            if key in details:
                if 'Brand' in details[key]:
                    brand = details[key]['Brand']
                elif 'Brand Name' in details[key]:
                    brand = details[key]['Brand Name']
                elif 'Manufacturer' in details[key]:
                    brand = details[key]['Manufacturer']
                
                if 'Model' in details[key]:
                    _model = details[key]['Model']
                elif 'Item model name' in details[key]:
                    _model = details[key]['Item model name']
            else:
                # Get it from byline_info
                byline_info = json.loads(instance.byline_info)
                if byline_info not in (None, {}, "{}", "") and 'info' in byline_info:
                    brand = byline_info['info']
                    if brand.startswith("Visit the "):
                        brand = brand.replace("Visit the ", "")
                        if brand.strip()[-1] == 'store':
                            brand = brand.replace(' store', '')
        
        if brand is not None and _model is not None:
            # Update
            setattr(instance, 'brand', brand)
            setattr(instance, 'model', _model)
            try:
                session.commit()
            except Exception as ex:
                session.rollback()
                print(ex)


def update_completed(session, table='ProductDetails'):
    from sqlalchemy import func

    instances = session.query(table_map[table]).all()
    count = 0
    for instance in instances:
        flag = True
        if instance.completed is None or instance.completed == False:
            if instance.num_reviews <= 1000:
                num_reviews = instance.num_reviews
                nr = -1
                with SqliteDict('cache.sqlite3') as mydict:
                    if f"NUM_REVIEWS_{instance.product_id}" in mydict:
                        nr = mydict[f"NUM_REVIEWS_{instance.product_id}"]
                        if not isinstance(nr, int):
                            nr = 1000
                    else:
                        flag = False
                if nr > -1:
                    num_reviews = nr
                if flag == False:
                    continue
                num_reviews_not_none = 0
                num_reviews_none = session.query(table_map['Reviews']).filter(Reviews.product_id == instance.product_id, Reviews.page_num == None).count()
                if num_reviews_none == 0:
                    num_reviews_not_none = session.query(table_map['Reviews']).filter(Reviews.product_id == instance.product_id, Reviews.page_num != None).count()
                
                if num_reviews_none >= round(int(0.85 * num_reviews)) or num_reviews_not_none >= round(int(0.85 * num_reviews)):
                    logger.info(f"{count} - ID {instance.product_id}: Marking as complete...")
                    instance.completed = True
                    try:
                        session.commit()
                        count += 1
                    except Exception as ex:
                        session.rollback()
                        print(ex)
            else:
                # Gt than 1000
                num_reviews = 1000
                nr = -1
                with SqliteDict('cache.sqlite3') as mydict:
                    if f"NUM_REVIEWS_{instance.product_id}" in mydict:
                        nr = mydict[f"NUM_REVIEWS_{instance.product_id}"]
                        if not isinstance(nr, int):
                            nr = 1000
                if nr > -1:
                    num_reviews = nr
                num_reviews_not_none = 0
                num_reviews_none = session.query(table_map['Reviews']).filter(Reviews.product_id == instance.product_id, Reviews.page_num == None).count()
                if num_reviews_none == 0:
                    num_reviews_not_none = session.query(table_map['Reviews']).filter(Reviews.product_id == instance.product_id, Reviews.page_num != None).count()
                if num_reviews_none >= round(int(0.9 * num_reviews)) or num_reviews_not_none >= round(int(0.9 * num_reviews)):
                    logger.info(f"{count} - ID {instance.product_id}: Marking as complete...")
                    instance.completed = True
                    try:
                        session.commit()
                        count += 1
                    except Exception as ex:
                        session.rollback()
                        print(ex)



def find_incomplete(session, table='ProductDetails'):
    instances = session.query(table_map[table]).all()
    count = 0
    pids = []
    for instance in instances:
        if instance.completed == True:
            if instance.num_reviews >= 1000:
                num_reviews = instance.num_reviews
                num_reviews_not_none = 0
                num_reviews_none = session.query(table_map['Reviews']).filter(Reviews.product_id == instance.product_id, Reviews.page_num == None, Reviews.review_date >= datetime.date(2020, 7, 1)).count()
                if num_reviews_none == 0:
                    num_reviews_not_none = session.query(table_map['Reviews']).filter(Reviews.product_id == instance.product_id, Reviews.page_num != None, Reviews.review_date >= datetime.date(2020, 7, 1)).count()
                
                if max(num_reviews_none, num_reviews_not_none) >= 900 and max(num_reviews_none, num_reviews_not_none) <= 1040:
                    logger.info(f"{count} - ID {instance.product_id}: Incomplete...")
                    pids.append(instance.product_id)
    return pids


def assign_subcategories(session, category, subcategory, table='ProductDetails'):
    from bs4 import BeautifulSoup

    import parse_data

    DUMP_DIR = os.path.join(os.getcwd(), 'dumps')

    if not os.path.exists(DUMP_DIR):
        return

    files = glob.glob(f"{DUMP_DIR}/{category}_{subcategory}_*")
    
    curr = 1

    for filename in files:
        with open(filename, 'r') as f:
            html = f.read()

        soup = BeautifulSoup(html, 'lxml')
        product_info, _ = parse_data.get_product_info(soup)

        for title in product_info:
            product_id = product_info[title]['product_id']
            if product_id is None:
                continue
            print(curr, product_id, title)
            curr += 1
            obj = query_table(session, 'ProductDetails', 'one', filter_cond=({'product_id': product_id}))
            if obj is not None:
                if obj.subcategories in ([], None):
                    obj.subcategories = json.dumps([subcategory])
                else:
                    subcategories = json.loads(obj.subcategories)
                    if subcategory in subcategories:
                        continue
                    subcategories.append(subcategory)
                    obj.subcategories = json.dumps(subcategories)
                try:
                    session.commit()
                except Exception as ex:
                    session.rollback()
                    print(ex)
        name = filename.split('/')[-1]
        os.rename(filename, os.path.join(DUMP_DIR, f"archived_{name}"))
    
    if category == "headphones":
        queryset = session.query(ProductListing).filter(ProductListing.category == category)
        pids = dict()
        for obj in queryset:
            pids[obj.product_id] = obj.price
        
        if subcategory == "tws":
            for pid in pids:
                instance = session.query(ProductDetails).filter(ProductDetails.product_id == pid).first()
                if instance is not None:
                    title = instance.product_title.lower()
                    if ("tws" in title) or ("true wireless" in title) or ("truly wireless" in title) or ("true-wireless" in title):
                        if instance.subcategories in ([], None):
                            instance.subcategories = json.dumps([subcategory])
                        else:
                            subcategories = json.loads(instance.subcategories)
                            if subcategory in subcategories:
                                continue
                            subcategories.append(subcategory)
                            instance.subcategories = json.dumps(subcategories)
                        logger.info(f"Set {title} as TWS subcategory")
            
            try:
                session.commit()
                logger.info(f'Updated subcategories for {subcategory}')
            except Exception as ex:
                session.rollback()
                logger.critical(f"Exception during commiting: {ex}")
        
        if subcategory == "price":
            for pid, price in pids.items():
                instance = session.query(ProductDetails).filter(ProductDetails.product_id == pid).first()
                if instance is not None:
                    if price is None:
                        continue
                    if price < 500:
                        price_subcategory = "<500"
                    elif price >= 500 and price < 1000:
                        price_subcategory = "500-1000"
                    elif price >= 1000 and price < 2000:
                        price_subcategory = "1000-2000"
                    elif price >= 2000 and price < 3000:
                        price_subcategory = "2000-3000"
                    elif price >= 3000 and price <= 5000:
                        price_subcategory = "3000-5000"
                    elif price > 5000:
                        price_subcategory = ">5000"
                    else:
                        continue
                    
                    if instance.subcategories in ([], None):
                        instance.subcategories = json.dumps([price_subcategory])
                    else:
                        subcategories = json.loads(instance.subcategories)
                        if subcategory in subcategories:
                            continue
                        subcategories.append(price_subcategory)
                        instance.subcategories = json.dumps(subcategories)
            
            try:
                session.commit()
                logger.info(f'Updated subcategories for {subcategory}')
            except Exception as ex:
                session.rollback()
                logger.critical(f"Exception during commiting: {ex}")


def update_date(session):
    objs = query_table(session, 'ProductDetails', 'all')
    count = 0
    incorrect = 0
    for obj in objs:
        if obj.date_completed is None:
            continue
        try:
            i = session.query(Reviews).filter(Reviews.product_id == obj.product_id).order_by(desc('review_date')).first()
            if i is not None:
                obj.date_completed = i.review_date
                try:
                    session.commit()
                    count += 1
                    print(count)
                except Exception as ex:
                    session.rollback()
                    print(ex)
            else:
                incorrect += 1
                print(f"Incorrect - {incorrect}: Possible integrityError with PID {obj.product_id}")
        except Exception as ex:
            print(ex)
            continue


def update_product_listing_from_cache(session, category, cache_file='cache.sqlite3'):
    from sqlitedict import SqliteDict

    count = 0

    with SqliteDict(cache_file, autocommit=False) as mydict:
        today = datetime.datetime.today().strftime("%d-%m-%y")

        for page in range(1, 100+1):
            key = f"LISTING_{category}_PAGE_{page}_{today}"
            listing = mydict.get(key)
            if listing is None:
                continue

            # Update ProductListing
            status = insert_product_listing(session, listing)
            if not status:
                logger.warning(f"Error when updating listing details for PAGE {page}")
            else:
                count += 1
    
    logger.info(f"Successfully updated {count} products for category = {category}")


def insert_short_titles(session):
    def foo(product_title):
        if product_title is None:
            return product_title
        
        if product_title.startswith('(Renewed)'):
            product_title = product_title[9:].strip()
        
        result = product_title.lower()
        # Order matters
        DELIMITERS = ['tws', 'true', 'wired', 'wireless', 'in-ear', 'in ear', 'on-ear', 'on ear'] + ['with', '[', '{', '(', ',']
        slen = len(result)
        fin = result
        temp = fin
        for delim in DELIMITERS:
            if result.startswith(delim):
                result = result[len(delim):].strip()
            bar = result.split(delim)
            if len(bar) == 1:
                # Empty
                continue
            short_title = bar[0].strip()
            
            if len(short_title) < slen:
                temp = fin
                fin = short_title.strip()
                slen = len(short_title)
        
        fin = fin.strip()
        if len(fin) == 0:
            print(f"For title {product_title}, len = 0")
        if len(fin.split()) <= 1:
            # Let's take the second shortest one instead, as fin is too short
            if len(temp.split()) <= 1:
                pass
            else:
                fin = temp.strip()
        if len(fin) > 0 and fin[-1] in [',', '.', ':', '-']:
            fin = fin[:-1]
        return fin
    
    queryset = session.query(ProductListing).all()

    for obj in queryset:
        if hasattr(obj, 'short_title'):
            setattr(obj, 'short_title', foo(obj.title))
    
    try:
        session.commit()
        logger.info("Updated short_title field!")
    except:
        session.rollback()
        logger.critical(f"Error during updating short_title field")


def mark_duplicates(session, category, table='ProductListing'):
    from sqlalchemy import asc, desc

    _table = table_map[table]
    
    queryset = session.query(_table).filter(_table.category == category, _table.is_duplicate == None, _table.total_ratings != None, _table.price != None, _table.title != None).order_by(asc('title')).order_by(desc('total_ratings')).order_by(desc('price'))

    reviews = {}
    pids = {}
    
    """
    for obj in queryset:
        short_title = ' '.join(word.lower() for word in obj.title.split()[:6])
        if short_title not in reviews:
            reviews[short_title] = session.query(table_map['Reviews']).filter(Reviews.product_id == obj.product_id, Reviews.is_duplicate != True).count()
            pids[obj.product_id] = short_title 
        else:
            db_reviews = session.query(table_map['Reviews']).filter(Reviews.product_id == obj.product_id, Reviews.is_duplicate != True).count()
            if reviews[short_title] >= db_reviews:
                num_reviews = reviews[short_title]
            else:
                num_reviews = db_reviews
                pids[obj.product_id] = short_title
            
            reviews[short_title] = num_reviews
    """
    
    prev = None

    duplicates = set()

    for idx, obj in enumerate(queryset):
        if idx == 0:
            prev = obj
            continue

        
        a = obj.short_title == prev.short_title

        b = ((abs(obj.total_ratings - prev.total_ratings) / max(obj.total_ratings, prev.total_ratings)) < 0.1)
        c = ((abs(obj.price - prev.price) / max(obj.price, prev.price)) < 0.1)

        if ((a & b) | (b & c) | (c & a)):
            # Majority Function
            duplicates.add(prev.product_id)
            duplicates.add(obj.product_id)
            continue

            if prev.product_id not in pids:
                obj.is_duplicate = True
                logger.info(f"Found duplicate - {obj.product_id} with prev id {prev.product_id}")
                try:
                    session.commit()
                except:
                    session.rollback()
                    logger.critical(f"Error during updating duplicate ID for product - {obj.product_id}")
        
        prev = obj
    
    from sqlitedict import SqliteDict

    with SqliteDict('cache.sqlite3', autocommit=True) as mydict:
        mydict[f'DUPLICATE_SET_{category}'] = duplicates


def mark_duplicate_reduced(session, category):
    from sqlitedict import SqliteDict

    with SqliteDict('cache.sqlite3', autocommit=False) as mydict:
        duplicates = mydict.get(f'DUPLICATE_SET_{category}')
    
    if duplicates is None:
        return

    pids = {}
    reviews = {}

    for pid in duplicates:
        obj = session.query(table_map['ProductListing']).filter(ProductListing.product_id == pid).first()
        if obj is None:
            continue

        short_title = obj.short_title
        if short_title not in reviews:
            reviews[short_title] = session.query(table_map['Reviews']).filter(Reviews.product_id == obj.product_id, Reviews.is_duplicate != True).count()
            pids[obj.product_id] = short_title 
        else:
            db_reviews = session.query(table_map['Reviews']).filter(Reviews.product_id == obj.product_id, Reviews.is_duplicate != True).count()
            if reviews[short_title] >= db_reviews:
                num_reviews = reviews[short_title]
            else:
                num_reviews = db_reviews
                pids[obj.product_id] = short_title
            
            reviews[short_title] = num_reviews

    with SqliteDict('cache.sqlite3', autocommit=True) as mydict:
        mydict[f'NON_DUPLICATE_SET_{category}'] = [pid for pid in pids]
    
    count = 0
    
    for pid in duplicates:
        if pid not in pids:
            # Duplicate
            obj = session.query(table_map['ProductListing']).filter(ProductListing.product_id == pid).first()
            if obj is None:
                continue
            setattr(obj, 'is_duplicate', True)
            try:
                session.commit()
                logger.info(f"Marked {pid} as duplicate!")
                count += 1
            except:
                session.rollback()
                logger.critical(f"Error when marking {pid} as duplicate")
    
    logger.info(f"Marked {count} products as duplicate!")


def update_duplicate_set_old(session, table='ProductListing', insert=False):
    from sqlalchemy import asc, desc, func
    from sqlitedict import SqliteDict

    _table = table_map[table]

    try:
        num_sets = session.query(func.max(ProductListing.duplicate_set)).scalar()
    except Exception as ex:
        logger.critical(f"Exception during fetching maximum value: {ex}")
        return

    queryset = session.query(_table).filter(ProductListing.duplicate_set.isnot(None), ~(ProductListing.is_duplicate.is_(True))).order_by(asc('category')).order_by(asc('short_title')).order_by(desc('total_ratings')).order_by(asc('title')).order_by(desc('price'))

    null_queryset = session.query(_table).filter(ProductListing.duplicate_set == None).order_by(asc('category')).order_by(asc('short_title')).order_by(desc('total_ratings')).order_by(asc('title')).order_by(desc('price'))

    temp = {}

    inserted_items = []
    inserted_idxs = []
    
    with SqliteDict('cache.sqlite3', autocommit=True) as cache:
        idxs = cache.get(f'PRODUCTLISTING_DUPLICATE_INDEXES')
        
        if idxs is None:
            idxs = {}
        
        idx = num_sets

        flag = False
        
        for instance in null_queryset:
            for obj in queryset:
                # TODO: Set this back to 0
                DELTA = 0.1

                # Find duplicate set
                a = (obj.short_title == instance.short_title)
                A_PRICE = obj.old_price if obj.old_price is not None else obj.price
                B_PRICE = instance.old_price if instance.old_price is not None else instance.price
                
                b = ((A_PRICE == B_PRICE) or (A_PRICE is not None and B_PRICE is not None and abs(A_PRICE - B_PRICE) <= (DELTA) * (max(A_PRICE, B_PRICE))))
                
                A_PRICE = obj.price
                B_PRICE = instance.price
                
                b_prime = ((A_PRICE == B_PRICE) or (A_PRICE is not None and B_PRICE is not None and abs(A_PRICE - B_PRICE) <= (DELTA) * (max(A_PRICE, B_PRICE))))

                b = b | b_prime

                c = ((obj.total_ratings == instance.total_ratings) or (obj.total_ratings is not None and instance.total_ratings is not None and instance.total_ratings is not None and abs(obj.total_ratings - instance.total_ratings) <= (0.1 + DELTA) * (max(obj.total_ratings, instance.total_ratings))))

                d = (obj.avg_rating == instance.avg_rating)

                if obj.total_ratings is not None and obj.total_ratings <= 100 and instance.total_ratings is not None and instance.total_ratings <= 100:
                    c = ((obj.total_ratings == instance.total_ratings) or (obj.total_ratings is not None and instance.total_ratings is not None and abs(obj.total_ratings - instance.total_ratings) <= 5))
                    flag = ((a & d) | (d & c) | (c & a))
                else:
                    flag = ((a & d) | (d & c) | (c & a))
                    if not flag:
                        override = c & (obj.avg_rating is not None and instance.avg_rating is not None and abs(obj.avg_rating - instance.avg_rating) <= 0.1)
                        if override:
                            flag = True

                if flag and not a:
                    # Be a bit careful
                    if ''.join(obj.short_title.split(' ')[:2]) != ''.join(instance.short_title.split(' ')[:2]):
                        # Check ProductDetails brand
                        obj1 = session.query(ProductDetails).filter(ProductDetails.product_id == obj.product_id).first()
                        obj2 = session.query(ProductDetails).filter(ProductDetails.product_id == instance.product_id).first()

                        if obj1 is not None and obj2 is not None and obj1.brand == obj2.brand:
                            pass
                        else:
                            # False positive
                            logger.warning(f"WARNING: PIDS {obj.product_id} and {instance.product_id} were FALSE positives")
                            logger.warning(f"WARNING: Titles {obj.short_title} and {instance.short_title} didn't match")
                            flag = False
                
                if not flag:
                    # No match
                    continue
                else:
                    idxs[instance.product_id] = obj.duplicate_set
                    temp[instance.product_id] = obj.duplicate_set
                    break
            
            if flag == False:
                # Check with the previously inserted items
                dup = False
                for _obj in inserted_items:
                    DELTA = 0.1

                    # Find duplicate set
                    a = (_obj.short_title == instance.short_title)
                    A_PRICE = _obj.old_price if _obj.old_price is not None else _obj.price
                    B_PRICE = instance.old_price if instance.old_price is not None else instance.price
                    
                    b = ((A_PRICE == B_PRICE) or (A_PRICE is not None and B_PRICE is not None and abs(A_PRICE - B_PRICE) <= (DELTA) * (max(A_PRICE, B_PRICE))))
                    
                    A_PRICE = _obj.price
                    B_PRICE = instance.price
                    
                    b_prime = ((A_PRICE == B_PRICE) or (A_PRICE is not None and B_PRICE is not None and abs(A_PRICE - B_PRICE) <= (DELTA) * (max(A_PRICE, B_PRICE))))

                    b = b | b_prime

                    c = ((_obj.total_ratings == instance.total_ratings) or (instance.total_ratings is not None and instance.total_ratings is not None and abs(_obj.total_ratings - instance.total_ratings) <= (DELTA) * (max(_obj.total_ratings, instance.total_ratings))))
                    
                    d = (_obj.avg_rating == instance.avg_rating)

                    dup = ((a & b) | (b & c) | (c & a))
                    
                    if _obj.total_ratings is not None and _obj.total_ratings <= 100 and instance.total_ratings is not None and instance.total_ratings <= 100:
                        c = ((_obj.total_ratings == instance.total_ratings) or (_obj.total_ratings is not None and instance.total_ratings is not None and abs(_obj.total_ratings - instance.total_ratings) <= 5))
                        dup = ((a & d) | (d & c) | (c & a))
                    else:
                        dup = ((a & d) | (d & c) | (c & a))
                        if not dup:
                            override = c & (_obj.avg_rating is not None and instance.avg_rating is not None and abs(_obj.avg_rating - instance.avg_rating) <= 0.1)
                            if override:
                                dup = True

                    if dup and not a:
                        # Be a bit careful
                        if ''.join(_obj.short_title.split(' ')[:2]) != ''.join(instance.short_title.split(' ')[:2]):
                            # Check ProductDetails brand
                            obj1 = session.query(ProductDetails).filter(ProductDetails.product_id == _obj.product_id).first()
                            obj2 = session.query(ProductDetails).filter(ProductDetails.product_id == instance.product_id).first()

                            if obj1 is not None and obj2 is not None and obj1.brand == obj2.brand:
                                pass
                            else:
                                # False positive
                                logger.warning(f"WARNING: PIDS {_obj.product_id} and {instance.product_id} were FALSE positives")
                                logger.warning(f"WARNING: Titles {_obj.short_title} and {instance.short_title} didn't match")
                                dup = False
                    
                    if not dup:
                        # No match
                        continue
                    else:
                        idxs[instance.product_id] = _obj.duplicate_set
                        temp[instance.product_id] = _obj.duplicate_set
                        break
                
                if dup == False:
                    idx += 1
                    idxs[instance.product_id] = idx
                    temp[instance.product_id] = idx
                    inserted_items.append(instance)
                    inserted_idxs.append(idx)
        
        cache[f'PRODUCTLISTING_DUPLICATE_INDEXES'] = idxs

    if insert == True:
        logger.info(f"Inserting indexes into the DB...")
        
        for product_id in temp:
            instance = session.query(_table).filter(_table.product_id == product_id).first()
            if instance:
                setattr(instance, 'duplicate_set', temp[product_id])

        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.critical(f"Exception: {ex} when trying to commit idxs")
        
        logger.info(f"Finished inserting!")


def index_duplicate_sets_old(session, table='ProductListing', insert=False, strict=False):
    from sqlalchemy import asc, desc
    from sqlitedict import SqliteDict

    _table = table_map[table]

    queryset = session.query(_table).order_by(asc('category')).order_by(asc('short_title')).order_by(desc('total_ratings')).order_by(asc('title')).order_by(desc('price'))
    
    with SqliteDict('cache.sqlite3', autocommit=True) as cache:
        idxs = {}
        info = {}

        prev = None

        idx = 1
        
        for obj in queryset:
            if prev is None:
                prev = obj
                continue

            # TODO: Set this back to 0
            if strict == False:
                DELTA = 0.1
            else:
                DELTA = 0.08

            # Find duplicate set
            a = (obj.short_title == prev.short_title)
            
            #A_PRICE = obj.old_price if obj.old_price is not None else obj.price
            #B_PRICE = prev.old_price if prev.old_price is not None else prev.price
            
            #b = ((A_PRICE == B_PRICE) or (A_PRICE is not None and B_PRICE is not None and abs(A_PRICE - B_PRICE) <= (DELTA) * (max(A_PRICE, B_PRICE))))
            
            #A_PRICE = obj.price
            #B_PRICE = prev.price
            
            #b_prime = ((A_PRICE == B_PRICE) or (A_PRICE is not None and B_PRICE is not None and abs(A_PRICE - B_PRICE) <= (DELTA) * (max(A_PRICE, B_PRICE))))

            #b = b | b_prime
            
            c = ((obj.total_ratings == prev.total_ratings) or (obj.total_ratings is not None and prev.total_ratings is not None and abs(obj.total_ratings - prev.total_ratings) <= (DELTA) * (max(obj.total_ratings, prev.total_ratings))))

            d = (obj.avg_rating == prev.avg_rating)

            if obj.total_ratings is not None and obj.total_ratings <= 100 and prev.total_ratings is not None and prev.total_ratings <= 100:
                c = ((obj.total_ratings == prev.total_ratings) or (obj.total_ratings is not None and prev.total_ratings is not None and abs(obj.total_ratings - prev.total_ratings) <= 5))
                flag = ((a & d) | (d & c) | (c & a))
            else:
                flag = ((a & d) | (d & c) | (c & a))
                if not flag:
                    override = c & (obj.avg_rating is not None and prev.avg_rating is not None and abs(obj.avg_rating - prev.avg_rating) <= 0.1)
                    if override:
                        flag = True

            if flag and not a:
                # Be a bit careful
                if ''.join(obj.short_title.split(' ')[:2]) != ''.join(prev.short_title.split(' ')[:2]):
                    # Check ProductDetails brand
                    obj1 = session.query(ProductDetails).filter(ProductDetails.product_id == obj.product_id).first()
                    obj2 = session.query(ProductDetails).filter(ProductDetails.product_id == prev.product_id).first()

                    if obj1 is not None and obj2 is not None and obj1.brand == obj2.brand:
                        pass
                    else:
                        # False positive
                        logger.warning(f"WARNING: PIDS {obj.product_id} and {prev.product_id} were FALSE positives")
                        logger.warning(f"WARNING: Titles {obj.short_title} and {prev.short_title} didn't match")
                        flag = False
            
            if not flag:
                # No match
                idxs[prev.product_id] = idx
                idx += 1
                idxs[obj.product_id] = idx
            else:
                idxs[prev.product_id] = idx
                idxs[obj.product_id] = idx
            
            if idx not in info:
                if flag == True:
                    info[idx] = [{'id': prev.product_id, 'title': prev.short_title}, {'id': obj.product_id, 'title': obj.short_title}]
                else:
                    info[idx] = [{'id': prev.product_id}]
                    info[idx + 1] = [{'id': obj.product_id, 'title': obj.short_title}]
            else:
                if flag == True:
                    info[idx].extend([{'id': prev.product_id, 'title': prev.short_title}, {'id': obj.product_id, 'title': obj.short_title}])
                else:
                    info[idx].extend([{'id': prev.product_id, 'title': prev.short_title}])
                    info[idx + 1] = [{'id': obj.product_id, 'title': obj.short_title}]

            prev = obj
        
        cache[f'PRODUCTLISTING_DUPLICATE_INDEXES'] = idxs
        cache[f'PRODUCTLISTING_DUPLICATE_INFO'] = info

    logger.info(f"Got {idx} number of sets. Finished indexing all duplicate sets!")

    if insert == True:
        logger.info(f"Inserting indexes into the DB...")
        
        with SqliteDict('cache.sqlite3', autocommit=False) as cache:
            idxs = cache.get(f"PRODUCTLISTING_DUPLICATE_INDEXES")
            if not idxs:
                logger.warning("idxs is None")
            else:
                for product_id in idxs:
                    instance = session.query(_table).filter(_table.product_id == product_id).first()
                    if instance:
                        setattr(instance, 'duplicate_set', idxs[product_id])

        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.critical(f"Exception: {ex} when trying to commit idxs")
        
        logger.info(f"Finished inserting!")


def update_duplicate_set(session, table='ProductListing', insert=False, strict=False, very_strict=False):
    return index_duplicate_sets(session, table='ProductListing', insert=insert, strict=strict, index_all=False, very_strict=very_strict)


def index_duplicate_sets(session, table='ProductListing', insert=False, strict=False, index_all=True, very_strict=False):
    import time

    from sqlalchemy import asc, desc, func
    from sqlitedict import SqliteDict

    _table = table_map[table]

    queryset = session.query(_table).order_by(asc('category')).order_by(asc('brand')).order_by(desc('total_ratings'))

    if index_all == False:
        queryset = session.query(_table).filter(ProductListing.duplicate_set == None).order_by(asc('category')).order_by(asc('brand')).order_by(desc('total_ratings'))
    else:
        queryset = session.query(_table).order_by(asc('category')).order_by(asc('brand')).order_by(desc('total_ratings'))
    
    if index_all == False:
        try:
            num_sets = session.query(func.max(ProductListing.duplicate_set)).scalar()
        except Exception as ex:
            logger.critical(f"Exception during fetching maximum value: {ex}")
            return
        if num_sets is None or num_sets <= 0:
            num_sets = 1
    else:
        num_sets = 1

    idx = num_sets

    info = {}

    if index_all == False:
        # Populate info with existing duplicate_set values
        non_null_queryset = session.query(_table).filter(ProductListing.duplicate_set != None).order_by(asc('category')).order_by(asc('brand')).order_by(desc('total_ratings'))
        info = {instance.product_id: instance.duplicate_set for instance in non_null_queryset if instance.duplicate_set is not None}

    DELTA = 0.1

    def get_max(info):
        maxval = num_sets
        for key in info:
            if info[key] > maxval:
                maxval = info[key]
        return maxval

    for obj1 in queryset:
        if obj1.product_id in info:
            continue
        
        q = session.query(_table).filter(ProductListing.category == obj1.category, ProductListing.brand == obj1.brand).order_by(desc('total_ratings'))
        
        duplicate_flag = False

        for obj2 in q:
            if obj1.product_id == obj2.product_id:
                continue
            
            a = (obj1.short_title == obj2.short_title)
            b = ((obj1.avg_rating == obj2.avg_rating) or (obj1.avg_rating is not None and obj2.avg_rating is not None and abs(obj1.avg_rating - obj2.avg_rating) <= (0.1)))
            c = ((obj1.total_ratings == obj2.total_ratings) or (obj1.total_ratings is not None and obj2.total_ratings is not None and abs(obj1.total_ratings - obj2.total_ratings) <= (DELTA) * (max(obj1.total_ratings, obj2.total_ratings))))

            if ((a & b) | (b & c) | (c & a)):
                # if b and c:
                duplicate_flag = True

                if duplicate_flag == True and (a == True and c == False):
                    # Suspicious
                    max_val = max(obj1.total_ratings, obj2.total_ratings)
                    if max_val > 1000:
                        if abs(obj1.total_ratings - obj2.total_ratings) > 60:
                            duplicate_flag = False
                    else:
                        if abs(obj1.total_ratings - obj2.total_ratings) > 20:
                            duplicate_flag = False
                
                if duplicate_flag == True and a == False:
                    # Try to compare model names if short title doesn't match
                    pattern = r'(([a-z\s\-\.\'(\d*\/+\d*)]+([0-9]\w*)))*[a-z\s\-\.\'\/]*'
                    try:
                        model_a = re.match(pattern, obj1.title.lower()).groups()[0].strip()
                    except:
                        model_a = obj1.short_title
                    try:
                        model_b = re.match(pattern, obj2.title.lower()).groups()[0].strip()
                    except:
                        model_b = obj2.short_title
                    
                    if model_a != model_b:
                        if b == True:
                            # Try stricter conditions
                            if obj1.total_ratings is not None and obj2.total_ratings is not None:
                                if obj1.total_ratings == obj2.total_ratings:
                                    pass
                                else:
                                    min_val = min(obj1.total_ratings, obj2.total_ratings)
                                    if min_val > 1000 and abs(obj1.total_ratings - obj2.total_ratings) > 500:
                                        duplicate_flag = False
                                    elif min_val > 100 and abs(obj1.total_ratings - obj2.total_ratings) > 50:
                                        duplicate_flag = False
                if c == False:
                    duplicate_flag = False
                
                if very_strict == True:
                    if duplicate_flag == True:
                        if obj1.total_ratings != obj2.total_ratings or obj1.avg_rating != obj2.avg_rating:
                            duplicate_flag = False
            
                if obj2.product_id in info:
                    info[obj1.product_id] = info[obj2.product_id]
                else:
                    idx = get_max(info)
                    info[obj1.product_id] = idx + 1
                    info[obj2.product_id] = idx + 1
                
                break
        
        if duplicate_flag == False:
            # Not a duplicate
            idx = get_max(info)
            info[obj1.product_id] = idx + 1
            idx += 1
    
    with SqliteDict('cache.sqlite3', autocommit=True) as mydict:
        mydict[f"DUPLICATE_INFO"] = info
    
    logger.info(f"Successfully indexed {idx} duplicate sets")

    if insert == True:
        logger.info(f"Inserting indexes into the DB...")
        
        with SqliteDict('cache.sqlite3', autocommit=True) as cache:
            if "DUPLICATE_INFO_OLD" not in cache:
                cache[f"DUPLICATE_INFO_OLD"] = {}

            idxs = cache.get(f"DUPLICATE_INFO")
            if not idxs:
                logger.warning("idxs is None")
            else:
                for product_id in idxs:
                    instance = session.query(_table).filter(_table.product_id == product_id).first()
                    if instance:
                        cache[f"DUPLICATE_INFO_OLD"][product_id] = instance.duplicate_set
                        setattr(instance, 'duplicate_set', idxs[product_id])

        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.critical(f"Exception: {ex} when trying to commit idxs")
        
        logger.info(f"Finished inserting!")       


def update_alert_flags(session, table='ProductListing'):
    # Set the alert flag
    logger.info(f"Updating alert flags into the DB...")
    
    from sqlalchemy import asc, desc, func
    from sqlitedict import SqliteDict

    _table = table_map[table]

    DELTA = 0.1

    queryset = session.query(_table).order_by(asc('category')).order_by(asc('brand')).order_by(desc('total_ratings'))

    for obj1 in queryset:
        q = session.query(_table).filter(ProductListing.category == obj1.category, ProductListing.brand == obj1.brand).order_by(desc('total_ratings'))
        
        duplicate_flag = False

        for obj2 in q:
            if obj1.product_id == obj2.product_id:
                continue
            
            a = (obj1.short_title == obj2.short_title)
            b = ((obj1.avg_rating == obj2.avg_rating) or (obj1.avg_rating is not None and obj2.avg_rating is not None and abs(obj1.avg_rating - obj2.avg_rating) <= (0.1)))
            c = ((obj1.total_ratings == obj2.total_ratings) or (obj1.total_ratings is not None and obj2.total_ratings is not None and abs(obj1.total_ratings - obj2.total_ratings) <= (DELTA) * (max(obj1.total_ratings, obj2.total_ratings))))

            if ((a & b) | (b & c) | (c & a)):
                # if b and c:
                duplicate_flag = True

                if duplicate_flag == True and (a == True and c == False):
                    # Suspicious
                    max_val = max(obj1.total_ratings, obj2.total_ratings)
                    if max_val > 1000:
                        if abs(obj1.total_ratings - obj2.total_ratings) > 60:
                            duplicate_flag = False
                    else:
                        if abs(obj1.total_ratings - obj2.total_ratings) > 20:
                            duplicate_flag = False
            
            if duplicate_flag == True:
                # They must belong to the same set
                if obj1.duplicate_set != obj2.duplicate_set:
                    obj1.alert = True
                    obj2.alert = True
            else:
                if obj1.duplicate_set == obj2.duplicate_set:
                    obj1.alert = True
                    obj2.alert = True

    try:
        session.commit()
    except Exception as ex:
        session.rollback()
        logger.critical(f"Exception: {ex} when trying to commit idxs")
    
    logger.info(f"Finished updating alerts!")


def test_indices(csv_file='ProductListing.csv'):
    import os

    import pandas as pd

    with SqliteDict('cache.sqlite3', autocommit=False) as mydict:
        info = mydict[f"DUPLICATE_INFO"]
    
    df1 = pd.read_csv(csv_file, sep=',', encoding='utf-8', delimiter='\n')
    
    df2 = pd.DataFrame(info.items(), columns=['product_id', 'duplicate_set'])

    cleaned_df = pd.merge(df1, df2.rename(columns={'duplicate_set': 'dup1'}), left_on='id', right_on='id1', how='left').drop('id1', 'dup1', axis=1)

    cleaned_df.to_csv(os.path.join(os.getcwd(), 'test.csv'), index=False)



def find_archived_products(session, table='ProductListing'):
    from sqlalchemy import asc, desc

    import cache

    cache = cache.Cache()
    cache.connect('master', use_redis=True)
    
    _table = table_map[table]

    queryset = session.query(_table).order_by(asc('category')).order_by(asc('short_title')).order_by(asc('duplicate_set')).order_by(desc('total_ratings'))

    prev = None

    count = 0
    
    for instance in queryset:
        if prev is None:
            prev = instance
            continue
        
        if prev.category == instance.category and prev.duplicate_set != instance.duplicate_set and prev.short_title == instance.short_title:
            # Possibly an archived product
            # Constraint: price(prev) >= price(curr), so prev is more recent
            cache.sadd(f"ARCHIVED_PRODUCTS_{instance.category}", instance.product_id)
            count += 1
            continue

        prev = instance
        continue

    logger.info(f"Found {count} archived products totally")


def sanity_check(session, categories, pids, table='ProductListing'):
    from sqlalchemy import asc, desc
    from sqlalchemy.sql.expression import func

    import cache

    max_set = session.query(func.max(ProductListing.duplicate_set))

    cache = cache.Cache()
    cache.connect('master', use_redis=True)
    
    _table = table_map[table]

    for category in categories:
        for idx in range(max_set + 1):
            queryset = session.query(_table).filter(ProductListing.duplicate_set == idx)
            set_count = queryset.count()
            if set_count == 0:
                continue
            elif set_count == 1:
                # Suspicious
                # Reindex this
                # TODO: Set duplicate_set of all such products to NULL and finally update indexes
                pass


def update_active_products(engine, pids, table='ProductListing', insert=True):
    engine.execute('UPDATE %s SET %s = %s' % (table, "is_active", "False"))
    
    for pid in pids:
        engine.execute('UPDATE %s SET %s = %s WHERE %s.product_id = "%s"' % (table, "is_active", "True", table, pid))


def index_qandas(engine, table='QandA'):
    engine.execute('UPDATE %s as t1 JOIN (SELECT product_id, duplicate_set FROM ProductListing) as t2 SET t1.duplicate_set = t2.duplicate_set WHERE t1.product_id = t2.product_id' % (table))


def index_reviews(engine, table='Reviews'):
    engine.execute('UPDATE %s as t1 JOIN (SELECT product_id, duplicate_set FROM ProductListing) as t2 SET t1.duplicate_set = t2.duplicate_set WHERE t1.product_id = t2.product_id' % (table))


def update_listing_completed(engine, table='ProductListing'):
    engine.execute('UPDATE %s as t1 JOIN (SELECT product_id, date_completed FROM ProductDetails) as t2 SET t1.date_completed = t2.date_completed WHERE t1.product_id = t2.product_id' % (table))


def transfer_brands(engine, table='ProductListing'):
    engine.execute('UPDATE %s as t1 JOIN (SELECT product_id, brand FROM ProductDetails) as t2 SET t1.brand = t2.brand WHERE t1.product_id = t2.product_id' % (table))


def update_brands(session, table='ProductListing', override=True):
    queryset = session.query(ProductListing).all()

    for instance in queryset:
        instance.brand = instance.short_title.split()[0]
    try:
        session.commit()
    except:
        session.rollback()
        logger.critical(f"Error when commiting for update_brands()")


def update_product_data(engine, dump=False):
    import os
    import subprocess

    import pandas as pd
    from decouple import config

    if dump == True:
        db_user = config('DB_USER')
        db_name = config('DB_NAME')
        db_host = config('DB_SERVER')
        db_port = config('DB_PORT')
        db_type = config('DB_TYPE')

        if db_type.startswith('mysql'):
            db_type = 'mysql'

        if db_type == 'mysql':
            # TODO: Remove the -p option and place the password under .my.cnf
            dump_command = f"""
            mysql -u {db_user} -p --database={db_name} --host={db_host} --port={db_port} --batch -e 
            "SELECT Reviews.id, Reviews.product_id, Reviews.rating, Reviews.review_date, Reviews.helpful_votes, Reviews.title, Reviews.body, Reviews.is_duplicate, Reviews.duplicate_set FROM Reviews 
            ORDER BY Reviews.duplicate_set asc, Reviews.title ASC, Reviews.review_date ASC, Reviews.title asc" | sed 's/\t/","/g;s/^/"/;s/$/"/;s/\n//g' > Reviews.csv
            """
        
            subprocess.Popen(dump_command)

            dump_command = f"""
            mysql -u {db_user} -p --database={db_name} --host={db_host} --port={db_port} --batch -e 
            "SELECT QandA.id, QandA.product_id, QandA.question, QandA.answer, QandA.date, QandA.is_duplicate, QandA.duplicate_set FROM QandA 
            ORDER BY QandA.duplicate_set asc, QandA.question ASC, QandA.answer ASC" | sed 's/\t/","/g;s/^/"/;s/$/"/;s/\n//g' > QandA.csv
            """
        
            subprocess.Popen(dump_command)


    QANDA_COMPRESSED = os.path.join(os.getcwd(), 'QandA.csv')

    if not os.path.exists(QANDA_COMPRESSED):
        raise ValueError("File not found")

    df = pd.read_csv(QANDA_COMPRESSED, sep=",", encoding="utf-8", lineterminator='\n', usecols=["id", "date", "question", "answer", "is_duplicate", "duplicate_set"])

    cleaned_df = df.drop_duplicates(subset=['date', 'question', 'answer', 'duplicate_set'], keep='first')

    cleaned_df['id'].to_csv(os.path.join(os.getcwd(), 'QandA_cleaned_ids.csv'), index=False)

    ids = ','.join(['"' + str(_id) + '"' for _id in cleaned_df['id']])

    engine.execute('UPDATE QandA SET is_duplicate = True')
    engine.execute('UPDATE QandA SET is_duplicate = False WHERE id in (%s)' % (ids))

    REVIEWS_COMPRESSED = os.path.join(os.getcwd(), 'Reviews.csv')

    if not os.path.exists(REVIEWS_COMPRESSED):
        raise ValueError("File not found")

    df = pd.read_csv(REVIEWS_COMPRESSED, sep=",", encoding="utf-8", usecols=["id", "review_date", "title", "body", "rating", "helpful_votes", "is_duplicate", "duplicate_set"])

    cleaned_df = df.drop_duplicates(subset=['review_date', 'title', 'body', 'rating', 'helpful_votes', 'duplicate_set'], keep='first')

    cleaned_df['id'].to_csv(os.path.join(os.getcwd(), 'Reviews_cleaned_ids.csv'), index=False)

    ids = ','.join(['"' + str(_id) + '"' for _id in cleaned_df['id']])

    engine.execute('UPDATE Reviews SET is_duplicate = True')
    engine.execute('UPDATE Reviews SET is_duplicate = False WHERE id in (%s)' % (ids))


def export_sets(session, cache_file='cache.sqlite3', category='headphones'):
    from sqlalchemy import asc, desc, func
    from sqlitedict import SqliteDict
    
    with SqliteDict(cache_file) as cache:
        results = cache.get(f"IMPORT_SETS_{category}")
    
    if results is None:
        return
    
    init_flag = True
    max_val = 1
    
    for pid in results:
        instance = session.query(ProductListing).filter(ProductListing.product_id == pid).first()
        dup_set = results[pid]['duplicate_set']
        if dup_set is None:
            if init_flag == True:
                init_flag = False
                max_val = session.query(func.max(ProductListing.duplicate_set)).scalar()
                
            max_val += 1
            instance.duplicate_set = max_val
        else:
            instance.duplicate_set = dup_set
        
        try:
            session.commit()
        except Exception as ex:
            session.rollback()
            logger.critical(f"Error when exporting duplicate sets: {ex}")


def import_from_csv(engine, table_name, csv_file):
    import pandas as pd

    if not os.path.exists(os.path.join(os.getcwd(), csv_file)):
        logger.critical(f"CSV File {csv_file} not found")
        raise ValueError

        
    df = pd.read_csv(csv_file, encoding="utf-8-sig")
    df.to_sql(table_name, engine, if_exists='append', index=False)
    logger.info(f"Successfully imported {table_name} from {csv_file}!")


def close_all_db_connections(engine, SessionFactory):
    SessionFactory.close_all()
    engine.dispose()
    logger.info(f"Closed all DB connections!")


if __name__ == '__main__':
    # Start a session using the existing engine
    parser = argparse.ArgumentParser()
    parser.add_argument('--index_duplicate_sets', help='Index Duplicate Sets', default=False, action='store_true')
    parser.add_argument('--update_duplicate_sets', help='Update Duplicate Sets', default=False, action='store_true')
    parser.add_argument('--strict', help='Apply very strict conditions on indexing', default=False, action='store_true')
    parser.add_argument('--index_qandas', help='Index Q and A', default=False, action='store_true')
    parser.add_argument('--index_reviews', help='Index Reviews', default=False, action='store_true')
    parser.add_argument('--update_listing_alerts', help='Update Listing Alerts', default=False, action='store_true')
    parser.add_argument('--update_product_data', help='Update Product Data (QandA and Reviews)', default=False, action='store_true')
    parser.add_argument('--update_product_listing_from_cache', help='Update Product Data from Cache', default=False, action='store_true')
    parser.add_argument('--update_active_products', help='Update Active Products (QandA and Reviews)', default=False, action='store_true')
    parser.add_argument('--find_archived_products', help='Find archived products from ProductListing', default=False, action='store_true')
    parser.add_argument('--transfer_brands', help='Transfer brands from ProductListing', default=False, action='store_true')
    parser.add_argument('--update_brands', help='Update brands in ProductListing', default=False, action='store_true')
    parser.add_argument('--test_indices', help='Test Indices', default=False, action='store_true')
    parser.add_argument('--export_sets', help='Export Sets', default=False, action='store_true')
    parser.add_argument('--import_from_csv', help='Import a Schema from a CSV file', default=False, action='store_true')
    parser.add_argument('--assign_subcategories', help='Assign Subcategories', default=False, action='store_true')
    parser.add_argument('--dump_from_cache', help='Dump from Cache', default=False, action='store_true')
    parser.add_argument('--close_all_db_connections', help='Forcibly close all DB connections', default=False, action='store_true')

    parser.add_argument('--csv', help='An external CSV file', type=str, default=None)
    parser.add_argument('--table', help='The database table', type=str, default=None)
    parser.add_argument('--export_to_csv', help='Export to CSV', default=False, action='store_true')

    args = parser.parse_args()

    _index_duplicate_sets = args.index_duplicate_sets
    _strict = args.strict
    _index_qandas = args.index_qandas
    _index_reviews = args.index_reviews
    _update_listing_alerts = args.update_listing_alerts
    _update_product_data = args.update_product_data
    _update_product_listing_from_cache = args.update_product_listing_from_cache
    _update_active_products = args.update_active_products
    _find_archived_products = args.find_archived_products
    _transfer_brands = args.transfer_brands
    _update_brands = args.update_brands
    _test_indices = args.test_indices
    _export_sets = args.export_sets
    _import_from_csv = args.import_from_csv
    _assign_subcategories = args.assign_subcategories
    _dump_from_cache = args.dump_from_cache
    _close_all_db_connections = args.close_all_db_connections
    _update_duplicate_sets = args.update_duplicate_sets

    _csv = args.csv
    _table = args.table
    _export_to_csv = args.export_to_csv

    from sqlalchemy import desc
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=True)

    session = Session()

    #instances = session.query(ProductDetails).filter(ProductListing.category == "headphones", ProductListing.product_id == ProductDetails.product_id, ProductDetails.completed == None)
    #print(", ".join(obj.product_id for obj in instances[30:50]))
    
    #update_completed(session)
    #for c in ["smartphones", "ceiling fan", "washing machine", "refrigerator"]:
    #    dump_from_cache(session, c, cache_file='cache.sqlite3')
    #update_brands_and_models(session, 'ProductDetails')
    
    """
    count = 0
    objs = query_table(session, 'ProductDetails', 'all')
    instances = session.query(ProductDetails).filter(ProductListing.category == "ceiling fan", ProductListing.product_id == ProductDetails.product_id)
    for obj in instances:
        if obj is not None:
            if obj.curr_price is None:
                continue
            price = int(round(obj.curr_price))
            
            if price < 1500:
                subcategory = "economy"
            elif price >= 4000:
                subcategory = "luxury"
            elif price >= 1500 and price < 2500:
                subcategory = "standard"
            elif price >= 2500 and price < 4000:
                subcategory = "premium"

            subcategories = obj.subcategories
            if subcategories is not None:
                subcategories = json.loads(subcategories)
                if subcategory not in subcategories:
                    subcategories.append(subcategory)
                    obj.subcategories = json.dumps(subcategories)
            else:
                obj.subcategories = json.dumps([subcategory])
            try:
                session.commit()
                count += 1
                print(f"{obj.product_title} {count}")
            except:
                session.rollback()
                print(ex)
    """
    #assign_subcategories(session, 'washing machine', 'fully automatic')

    #print(fetch_product_ids(session, 'ProductListing', 'books'))

    #column = Column('category', String(100))
    #add_column(engine, 'DailyProductListing', column)
    #column = Column('duplicate_set', Integer())
    #add_column(engine, 'ProductListing', column)
    #column = Column('is_duplicate', Boolean())
    #add_column(engine, 'ProductDetails', column)
    #update_date(session)
    #update_product_listing_from_cache(session, "headphones")
    #column = Column('short_title', String(100))
    #add_column(engine, 'ProductListing', column)
    #mark_duplicates(session, "headphones")
    #mark_duplicate_reduced(session, "headphones")
    #index_duplicate_sets(session, insert=True, strict=True)
    #update_duplicate_set(session, table='ProductListing', insert=True)
    #update_active_products(engine, ['B07X1KSWZ3'], table='ProductListing', insert=True)
    #index_qandas(engine)
    #index_reviews(engine)
    #update_product_data(engine, dump=False)
    #column = Column('date_completed', DateTime())
    #add_column(engine, 'ProductListing', column)
    if _export_to_csv == True:
        if _table is None or _csv is None:
            raise ValueError(f"Must specify the --table and --csv for exporting to csv")
        try:
            DB_USER = config('DB_USER')
            DB_PASSWORD = config('DB_PASSWORD')
            DB_PORT = config('DB_PORT')
            DB_NAME = config('DB_NAME')
            DB_SERVER = config('DB_SERVER')
            DB_TYPE = config('DB_TYPE')
            engine = db_manager.Database(dbtype=DB_TYPE, username=DB_USER, password=DB_PASSWORD, port=DB_PORT, dbname=DB_NAME, server=DB_SERVER).db_engine
        except:
            DB_TYPE = 'sqlite'
            engine = db_manager.Database(dbtype=DB_TYPE).db_engine
        results = pd.read_sql_query(f"SELECT * FROM {_table}", engine)
        results.to_csv(os.path.join(DATASET_PATH, f'{_csv}'), index=False, sep=",")
        exit(0)
    if _index_duplicate_sets == True:
        index_duplicate_sets(session, insert=True, strict=True, very_strict=_strict)
    if _update_duplicate_sets == True:
        update_duplicate_set(session, insert=True, strict=True, very_strict=_strict)
    if _index_qandas == True:
        index_qandas(engine)
    if _index_reviews == True:
        index_reviews(engine)
    if _update_listing_alerts == True:
        update_alert_flags(session)
    if _update_product_data == True:
        update_product_data(engine, dump=False)
    if _update_product_listing_from_cache == True:
        update_product_listing_from_cache(session, "headphones")
    if _update_active_products == True:
        import cache
        cache = cache.Cache()
        cache.connect('master', use_redis=True)
        category = "headphones"
        pids = cache.smembers(f"LISTING_{category}_PIDS")
        update_active_products(engine, pids)
    if _find_archived_products == True:
        find_archived_products(session)
    if _transfer_brands == True:
        transfer_brands(engine)
    if _update_brands == True:
        update_brands(session)
    if _test_indices == True:
        test_indices()
    if _export_sets == True:
        export_sets(session)
    if _import_from_csv == True:
        if _table is None or _csv is None:
            raise ValueError(f"Both --table and --csv flags must be given for importing from csv")
        table_name = _table
        csv_file = _csv
        import_from_csv(engine, table_name, csv_file)
    if _assign_subcategories == True:
        for category in subcategory_map:
            for subcategory in subcategory_map[category]:
                assign_subcategories(session, category, subcategory, table='ProductDetails')
    if _close_all_db_connections == True:
        close_all_db_connections(engine, Session)
    if _dump_from_cache == True:
        for c in ["headphones", "smartphones", "ceiling fan", "washing machine", "refrigerator"]:
            dump_from_cache(session, c, cache_file='cache.sqlite3')
    exit(0)
    #add_column(engine, 'SponsoredProductDetails', column)
    
    #alter_column(engine, 'ProductDetails', 'categories', 'subcategories', 'Text')
    #alter_column(engine, 'SponsoredProductDetails', 'categories', 'subcategories', 'Text')
    #column = Column('is_sponsored', Boolean(), unique=False, default=False)
    #add_column(engine, 'ProductDetails', column)
    #add_column(engine, 'SponsoredProductDetails', column)

    #obj = query_table(session, 'ProductListing', 'one', filter_cond=({'product_id': '8173711461'}))
    #objs = query_table(session, 'ProductListing', 'all', filter_cond=({'category': 'books'}))
    #objs = query_table(session, 'ProductListing', 'all', filter_cond=['in', 'category', (('books', 'mobile'))])
    #if objs is not None:
    #    for obj in objs: 
    #        print(obj.product_id, obj.title)
    #else:
    #    print("Nothing Found")

    with open('dumps/headphones.pkl', 'rb') as f:
        product_listing = pickle.load(f)

    #insert_daily_product_listing(session, product_listing)
    #insert_product_listing(session, product_listing)

    #with open('dumps/dump_B07DJLVJ5M.pkl', 'rb') as f:
    #    product_details = pickle.load(f)

    #insert_product_details(session, product_details, is_sponsored=False)

    #with open('dumps/dump_B07DJLVJ5M_qanda.pkl', 'rb') as f:
    #    qanda = pickle.load(f)

    #insert_product_qanda(session, qanda, product_id='B07DJLVJ5M')
