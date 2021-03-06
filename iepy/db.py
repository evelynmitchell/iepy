from collections import namedtuple
try:
    from functools import lru_cache
except:
    from functools32 import lru_cache

from mongoengine import connect as mongoconnect
from mongoengine.connection import get_db

from iepy.models import (
    IEDocument, PreProcessSteps, InvalidPreprocessSteps, TextSegment, Entity)


IEPYDBConnector = namedtuple('IEPYDBConnector', 'connector segments documents')

# Number of entities that will be cached on get_entity function.
ENTITY_CACHE_SIZE = 20  # reasonable compromise


def connect(db_name):
    return IEPYDBConnector(
        mongoconnect(db_name),
        TextSegmentManager(),
        DocumentManager(),
    )


class DocumentManager(object):
    """Wrapper to the db-access, so it's not that impossible to switch
    from mongodb to something else if desired.
    """

    ### Basic administration and pre-process

    def create_document(self, identifier, text, metadata=None):
        """Creates a new Document with text ready to be inserted on the
        information extraction pipeline (ie, ready to be tokenized, POS Tagged,
        etc).

        Identifier must be a unique value that will be used for distinguishing
        one document from another. If no title is given, will be inferred from
        the identifier.
        Metadata is a dictionary where you can put whaever you want to persist
        with your document. IEPy will do nothing with it except ensuring that
        such information will be preserved.
        """
        if metadata is None:
            metadata = {}
        doc = IEDocument(human_identifier=identifier, text=text, metadata=metadata)
        doc.save()
        return doc

    def __iter__(self):
        return IEDocument.objects.timeout(False).all()

    def get_raw_documents(self):
        """returns an interator of documents that lack the text field, or it's
        empty.
        """
        return IEDocument.objects(text='').timeout(False)

    def get_documents_lacking_preprocess(self, step):
        """Returns an iterator of documents that shall be processed on the given
        step."""
        if not isinstance(step, PreProcessSteps):
            raise InvalidPreprocessSteps
        query = {'preprocess_metadata__%s__exists' % step.name: False}
        return IEDocument.objects(**query).timeout(False)


class TextSegmentManager(object):

    def segments_with_both_entities(self, entity_a, entity_b):
        key_a, key_b = entity_a.key, entity_b.key
        return TextSegment.objects(entities__key=key_a)(entities__key=key_b)

    def segments_with_both_kinds(self, kind_a, kind_b):
        if kind_a != kind_b:
            return TextSegment.objects(entities__kind=kind_a)(entities__kind=kind_b)
        else:
            # Need a different query here, we need to check that the type
            # appears twice
            db = get_db()
            pipeline = [
                {'$match': {"entities.kind": kind_a}},
                {'$unwind': "$entities"},
                {'$group': {
                    '_id': {'_id': "$_id", 'k': "$entities.kind"},
                    'count': {'$sum': 1}
                }},
                {'$match': {'_id.k': kind_a, 'count': {'$gte': 2}}},
                {'$project': {'_id': 0, 'id': "$_id._id"}},
            ]

            objects = db.text_segment.aggregate(pipeline)
            segments = list(TextSegment.objects.in_bulk([c['id'] for c in objects[u'result']]).values())
            return segments


@lru_cache(maxsize=ENTITY_CACHE_SIZE)
def get_entity(kind, literal):
    return Entity.objects.get(kind=kind, key=literal)


def get_segment(document_identifier, offset):
    d = IEDocument.objects.get(human_identifier=document_identifier)
    return TextSegment.objects.get(document=d, offset=offset)
