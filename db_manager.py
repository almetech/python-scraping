# Represents all the Models used to create our scraper

import json
import pickle
import re
import sqlite3
from datetime import datetime

import pymysql
from decouple import UndefinedValueError, config
from sqlalchemy import (Boolean, Column, DateTime, Float, ForeignKey, Integer,
                        MetaData, String, Text, Table, create_engine, exc)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import mapper, relationship, sessionmaker

pymysql.install_as_MySQLdb()


tables = {
    'ProductListing': {
        'product_id': 'TEXT(16) PRIMARY KEY',
        'category': 'TEXT(60)',
        'title': 'TEXT(100)',
        'product_url': 'LONGTEXT',
        'avg_rating': 'FLOAT',
        'total_ratings': 'INTEGER',
        'price': 'INTEGER',
        'old_price': 'INTEGER',
        'secondary_information': 'LONGTEXT',
        'image': 'TEXT(500)',
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
        'reviews_url': 'TEXT(500)',
        'created_on': 'DATETIME',
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
    },
    'QandA': {
        'id': 'INTEGER PRIMARY KEY',
        'product_id': 'TEXT(16)',
        'question': 'LONGTEXT',
        'answer': 'LONGTEXT',
        'date': 'DATETIME',
        '_product_id': ['FOREIGN KEY', 'REFERENCES ProductListing (product_id)'],
    },
    'Reviews': {
        'id': 'INTEGER PRIMARY KEY',
        'product_id': 'TEXT(16)',
        'rating': 'FLOAT',
        'review_date': 'DATETIME',
        'country': 'TEXT(40)',
        'title': 'TEXT(500)',
        'body': 'LONGTEXT',
        'product_info': 'LONGTEXT',
        'verified_purchase': 'INTEGER',
        'helpful_votes': 'INTEGER',
        '_product_id': ['FOREIGN KEY', 'REFERENCES ProductListing (product_id)'],
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
    def __init__(self, dbtype='sqlite', username='', password='', dbname='', server=''):
        dbtype = dbtype.lower()
        if dbtype in self.DB_ENGINE.keys():
            engine_url = self.DB_ENGINE[dbtype].format(DB=dbname)
            self.db_engine = create_engine(engine_url)
        elif dbtype.startswith('mysql'):
            # mysql+pymysql also supported
            engine_url = f'{dbtype}://{username}:{password}@{server}'
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


# Base = declarative_base()


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


def create_tables(engine):
    Base.metadata.create_all(engine)


def insert_product_listing(session, data, table='ProductListing'):
    row = dict()
    for category in data:
        row['category'] = category
        for page_num in data[category]:
            for title in data[category][page_num]:
                row['title'] = title
                value = data[category][page_num][title]
                for key in value:
                    if value[key] is not None:
                        if key == 'avg_rating':
                            row[key] = float(value[key].split()[0])
                        elif key == 'total_ratings':
                            row[key] = int(value[key].replace(',', '').replace('.', ''))
                        elif key in ('price', 'old_price'):
                            row[key] = int(value[key][1:].replace(',', '').replace('.', ''))
                        else:
                            row[key] = value[key]
                    else:
                        row[key] = value[key]
                try:
                    if row['product_id'] is not None:
                        obj = ProductListing()
                        [setattr(obj, key, value) for key, value in row.items()]
                        session.add(obj)
                        session.commit()
                except exc.IntegrityError:
                    session.rollback()
                    result = session.query(ProductListing).filter_by(product_id=row['product_id']).first()
                    if result is None:
                        pass
                    else:
                        update_fields = (field for field in tables[table] if hasattr(result, field) and getattr(result, field) is None)
                        for field in update_fields:
                            setattr(result, field, row[field])
                        session.commit()


def insert_product_details(session, data, table='ProductDetails', is_sponsored=False):
    if is_sponsored == True:
        table = 'SponsoredProductDetails'

    row = {key: (data[key] if not (isinstance(data[key], list) or isinstance(data[key], dict)) else json.dumps(data[key])) for key in data}
    for field in row:
        if row[field] is not None:
            if field == 'num_reviews':
                row[field] = int(row[field].split()[0].replace(',', '').replace('.', ''))
            elif field in ('curr_price'):
                row[field] = float(row[field].replace(',', ''))
    row['created_on'] = datetime.now()
    try:
        if is_sponsored == True:
            obj = SponsoredProductDetails()
            [setattr(obj, key, value) for key, value in row.items()]
            session.add(obj)
        else:
            obj = ProductDetails()
            [setattr(obj, key, value) for key, value in row.items()]
            session.add(obj)
        session.commit()
    except exc.IntegrityError:
        session.rollback()
        result = session.query(ProductListing).filter_by(product_id=row['product_id']).first()
        update_fields = (field for field in tables[table] if hasattr(result, field) and getattr(result, field) is None)
        for field in update_fields:
            setattr(result, field, row[field])
        session.commit()


def insert_product_qanda(session, qanda, product_id, table='QandA'):
    for pair in qanda:
        row = {key: (value if not isinstance(value, list) and not isinstance(value, dict) else json.dumps(value)) for key, value in pair.items()}
        # Add product id
        row['product_id'] = product_id
        obj = QandA()
        [setattr(obj, key, val) for key, val in row.items()]
        session.add(obj)
    session.commit()


def insert_product_reviews(session, reviews, product_id, table='Reviews'):
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
        obj = Reviews()
        [setattr(obj, key, val) for key, val in row.items()]
        session.add(obj)
    session.commit()


if __name__ == '__main__':
    # Start a session using the existing engine
    Session = sessionmaker(bind=engine, autocommit=False, autoflush=True)

    session = Session()

    # with open('dumps/mobile.pkl', 'rb') as f:
    with open('dumps/phones.pkl', 'rb') as f:
        product_listing = pickle.load(f)

    insert_product_listing(session, product_listing)

    with open('dumps/dump_B07DJLVJ5M.pkl', 'rb') as f:
        product_details = pickle.load(f)

    insert_product_details(session, product_details, is_sponsored=False)

    with open('dumps/dump_B07DJLVJ5M_qanda.pkl', 'rb') as f:
        qanda = pickle.load(f)

    insert_product_qanda(session, qanda, product_id='B07DJLVJ5M')
