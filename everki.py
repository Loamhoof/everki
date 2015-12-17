import os
import re
from xml.etree import ElementTree

from yaml import load
from evernote.api.client import EvernoteClient
from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec
from evernote.edam.limits.constants import EDAM_USER_NOTES_MAX

from aqt import mw
from aqt.utils import showInfo
from aqt.qt import QAction, SIGNAL


def synchronize():
    # Open config
    config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
    with open(config_path) as config_file:
        config = load(config_file.read())

    # Init anki objects
    deck_id = mw.col.decks.id(config['params']['deck'])
    model = mw.col.models.byName(config['params']['note_type'])
    mw.col.models.setCurrent(model)

    # Store existing notes
    existing_notes = [
        dict(mw.col.getNote(note_id).items())
        for note_id in mw.col.findNotes('mid:%s tag:did:%s' % (model['id'], deck_id))
    ]

    # Init Evernote
    note_store = EvernoteClient(token=config['evernote_token'], sandbox=False).get_note_store()

    # Fetch Evernote notes lines
    note_filter = NoteFilter(order=1, ascending=True, words=config['params']['note_search_filter'])
    note_result_spec = NotesMetadataResultSpec(includeTitle=True)
    lines = (
        (content, note_metadata.title)
        for note_metadata in note_store.findNotesMetadata(note_filter, 0, EDAM_USER_NOTES_MAX, note_result_spec).notes
        for content in ElementTree.fromstring(note_store.getNoteContent(note_metadata.guid)).find('div').itertext()
    )

    # Parse those lines
    parsing_regex = re.compile(config['params']['parsing_regex'], re.UNICODE)
    matches = (
        (parsing_regex.match(line), title)
        for line, title in lines
    )
    mappings = (
        (match.groupdict(), title)
        for match, title in matches
        if match is not None
    )

    # Add the new notes
    added_notes, ignored_notes = [], []
    for mapping, title in mappings:
        if mapping not in existing_notes:
            note = mw.col.newNote()
            note.model()['did'] = deck_id
            note.addTag('did:%s' % deck_id)
            note.addTag('title:%s' % title.replace(' ', '_'))
            for key in note.keys():
                note[key] = mapping[key]
            mw.col.addNote(note)
            existing_notes.append(mapping)
            added_notes.append(mapping)
        else:
            ignored_notes.append(mapping)

    showInfo("""
        Synchronized.
        Added:""" + ''.join("""
         - %s""" % ', '.join(added_note.values()) for added_note in added_notes) + """
        Ignored:""" + ''.join("""
         - %s""" % ', '.join(ignored_note.values()) for ignored_note in ignored_notes))
    mw.reset()

action = QAction('Everki', mw)
mw.connect(action, SIGNAL('triggered()'), synchronize)
mw.form.menuTools.addAction(action)
