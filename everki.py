import os
import re
from xml.etree import ElementTree

from yaml import load
from evernote.api.client import EvernoteClient
from evernote.edam.type.ttypes import Note
from evernote.edam.notestore.ttypes import NoteFilter, NotesMetadataResultSpec
from evernote.edam.limits.constants import EDAM_USER_NOTES_MAX

from aqt import mw
from aqt.utils import showInfo
from aqt.qt import QAction, SIGNAL


# Open config
config_path = os.path.join(os.path.dirname(os.path.realpath(__file__)), 'config.yml')
with open(config_path) as config_file:
    config = load(config_file.read())

# Init Evernote
note_store = EvernoteClient(token=config['evernote_token'], sandbox=False).get_note_store()


def aggregate():
    # Init/Fetch the One note
    one_note_name = config['params']['one_note']
    one_note_filter = NoteFilter(words=one_note_name)
    one_note_result_spec = NotesMetadataResultSpec()
    one_note_search = note_store.findNotesMetadata(one_note_filter, 0, EDAM_USER_NOTES_MAX, one_note_result_spec)
    if one_note_search.totalNotes == 0:
        one_note_guid = note_store.createNote(Note(title=one_note_name)).guid
    else:
        one_note_guid = one_note_search.notes[0].guid
    one_note = note_store.getNote(one_note_guid, True, False, False, False)

    # Fetch Evernote notes lines
    note_filter = NoteFilter(order=1, ascending=True, words=config['params']['note_search_filter'])
    note_result_spec = NotesMetadataResultSpec()
    parsing_regex = re.compile(config['params']['parsing_regex'], re.UNICODE)
    notes_metadata = note_store.findNotesMetadata(note_filter, 0, EDAM_USER_NOTES_MAX, note_result_spec).notes
    lines = '<br />'.join(
        line.encode('UTF-8')
        for note_metadata in notes_metadata
        for line in ElementTree.fromstring(note_store.getNoteContent(note_metadata.guid)).find('div').itertext()
        if parsing_regex.match(line) is not None
    )

    # Append those lines to the One note content
    if len(lines):
        end_tag_index = one_note.content.find('</en-note>')
        one_note.content = one_note.content[:end_tag_index] + '<br />' + lines + one_note.content[end_tag_index:]

        # Update the One note
        note_store.updateNote(one_note)

    # Remove aggregated notes
    for note_metadata in notes_metadata:
        note_store.deleteNote(note_metadata.guid)

    showInfo("""
        Aggregated.
        """ + lines.decode('utf-8'))


def synchronize():
    # Init anki objects
    deck_id = mw.col.decks.id(config['params']['deck'])
    model = mw.col.models.byName(config['params']['note_type'])
    mw.col.models.setCurrent(model)

    # Store existing notes
    existing_notes = [
        dict(mw.col.getNote(note_id).items())
        for note_id in mw.col.findNotes('mid:%s tag:did:%s' % (model['id'], deck_id))
    ]

    # Fetch Evernote notes lines
    one_note_filter = NoteFilter(words=config['params']['one_note'])
    one_note_result_spec = NotesMetadataResultSpec()
    one_note_search = note_store.findNotesMetadata(one_note_filter, 0, EDAM_USER_NOTES_MAX, one_note_result_spec)
    one_note_guid = one_note_search.notes[0].guid
    lines = (
        line
        for line in ElementTree.fromstring(note_store.getNoteContent(one_note_guid)).itertext()
    )

    # Parse those lines
    parsing_regex = re.compile(config['params']['parsing_regex'], re.UNICODE)
    matches = (
        parsing_regex.match(line)
        for line in lines
    )
    mappings = (
        match.groupdict()
        for match in matches
        if match is not None
    )

    # Add the new notes
    added_notes, ignored_notes = [], []
    for mapping in mappings:
        if mapping not in existing_notes:
            note = mw.col.newNote()
            note.model()['did'] = deck_id
            note.addTag('did:%s' % deck_id)
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

aggregate_action = QAction('Everki: Aggregate', mw)
mw.connect(aggregate_action, SIGNAL('triggered()'), aggregate)
mw.form.menuTools.addAction(aggregate_action)
synchronize_action = QAction('Everki: Synchronize', mw)
mw.connect(synchronize_action, SIGNAL('triggered()'), synchronize)
mw.form.menuTools.addAction(synchronize_action)
