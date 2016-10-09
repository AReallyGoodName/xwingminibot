
import io
import itertools
import json
import logging as log
import re
import string
import time
import urllib.parse
import os

import praw

import credentials


reauth_sec = 60*20 # 20 min
# templates
signature = ("\n^(Call/)^[PM](https://www.reddit.com/message/compose/?to={})"
            " ^( me with up to 7 [[cardname]] PM [[info]])").format(credentials.username)

# files
CARDS_JSON = 'cards.json'
PILOT_TEXT_JSON = 'pilots-en.json'
UPGRADE_TEXT_JSON = 'upgrades-en.json'
MODIFICATION_TEXT_JSON = 'modifications-en.json'
TITLE_TEXT_JSON = 'titles-en.json'
INFO_MSG_TMPL = 'info_msg.templ'


def initReddit(refresh_token = credentials.refresh_token):
    """ get the reddit api token, see credentials.py for more info """

    log.debug("initReddit() creating reddit adapter")
    r = praw.Reddit(user_agent=credentials.user_agent)

    log.debug("initReddit() preparing reddit adapter")
    r.set_oauth_app_info(client_id=credentials.client_id,
                         client_secret=credentials.client_secret,
                         redirect_uri=credentials.redirect_uri)

    log.debug("initReddit() trying to authenticate with refresh token: %s", refresh_token)
    r.refresh_token = refresh_token
    r.refresh_access_information()

    if r.user.name != credentials.username:
        raise Exception('credentials and session usernames do not match')

    log.debug("initReddit() login success: %s", r.user.name)
    next_auth_time = int(time.time()) + reauth_sec
    return r, next_auth_time


def refreshReddit(r):
    """ keep the reddit api token alive """
    try:
        log.debug("refreshReddit() going to refresh with token %s", r.refresh_token)
        r.refresh_access_information()
        next_auth_time = int(time.time()) + reauth_sec
    except praw.errors.Forbidden as fe:
        # refreshing sometimes fails, our token got lost somewhere in the clouds
        log.error("refreshReddit() got forbidden, creating new connection with backup token")
        r, next_auth_time = initReddit(credentials.backup_refresh_token)
        log.info("refreshReddit() new connection seems to work")
        try:
            # this is just information, there is no need to act
            # the tokens are reusable multiple times and for months
            r.send_message(credentials.admin_username,
                            'backup token used',
                            'new init after failed refresh')
        except:
            pass
    return r, next_auth_time


def cleanName(name):
    """ we ignore all special characters, numbers, whitespace, case """
    return ''.join(char for char in name.lower() if char in (string.digits + string.ascii_lowercase))


def removeQuotes(text):
    """ removes quote blocks, the cards in them are already answered """
    lines = []
    for l in io.StringIO(text):
        l = l.strip()
        if l and l[0] != '>':
            lines.append(l)
    return ' '.join(lines)


def getTextForCards(card_db, cards):
    """ gets card formatted card text and signature and joins them """
    comment_text = ''
    for card in cards:
        log.info('getting text for %s', card)
        # Find cards containing the match
        for name, cardText in card_db.items():
            if len(card) > 2 and name.startswith(card):
                comment_text += cardText

    if comment_text:
        comment_text += signature

    comment_text = comment_text.replace('\n\n', '    \n')

    return comment_text


def getCardsFromComment(text, spell_check):
    log.info('getting cards from %s', text)

    """ look for [[cardname]] in text and collect them securely """
    cards = []
    if len(text) < 6:
        return cards
    open_bracket = False
    card = ''

    # could be regex, but I rather not parse everything evil users are sending
    for i in range(1, len(text)):
        c = text[i]
        if open_bracket and c != ']':
            card += c
        if c == '[' and text[i-1] == '[':
            open_bracket = True
        if c == ']' and open_bracket:
            if len(card) > 0:
                log.debug("adding a card: %s", card)
                cleanCard = cleanName(card)
                if cleanCard:
                    log.debug("cleaned card name: %s", cleanCard)
                    # slight spelling error?
                    # checkedCard = spell_check.correct(cleanCard)
                    checkedCard = cleanCard
                    if cleanCard != checkedCard:
                        log.info("spelling fixed: %s -> %s", cleanCard, checkedCard)
                    # add cardname
                    if checkedCard not in cards:
                        cards.append(checkedCard)
                    else:
                        log.info("duplicate card: %s", card)

            card = ''
            open_bracket = False
            if len(cards) >= 7:
                break

        if len(card) > 30:
            card = ''
            open_bracket = False

    log.info('got %i cards', len(cards))
    return cards


def loadCardDB():
    """ load and format cards from json files into dict """
    with open(CARDS_JSON, 'r') as infofile:
        cards = json.load(infofile)
    with open(PILOT_TEXT_JSON, 'r') as infofile:
        pilotTexts = json.load(infofile)
    with open(UPGRADE_TEXT_JSON, 'r') as infofile:
        upgradeTexts = json.load(infofile)
    with open(MODIFICATION_TEXT_JSON, 'r') as infofile:
        modificationTexts = json.load(infofile)
    with open(TITLE_TEXT_JSON, 'r') as infofile:
        titleTexts = json.load(infofile)
    return _createCardDB(cards, pilotTexts, upgradeTexts, modificationTexts, titleTexts)


def _createCardDB(cards, pilotTexts, upgradeTexts, modificationTexts, titleTexts):
    """ formats all the cards to text """
    # TODO cardDB should be an object by now instead of a dict
    card_db = {}
    initialisms_db = {}
    ship_db = {}

    for name, ship in cards['ships'].items():
        ship_db[name] = '{} ({}/{}/{}/{})'.format(name, ship.get('attack') or 0, ship['agility'], ship['hull'], ship['shields'])
        card_db[cleanName(name)] = '**' + ship_db[name] + '**\n\r\n'

    # fill templates
    for pilot in cards['pilotsById']:
        if not cleanName(pilot['name']) in card_db:
            card_db[cleanName(pilot['name'])] = ''
        card_db[cleanName(pilot['name'])] += '**' + '{}'.format(pilot['name']) + '**'
        if 'unique' in pilot:
            card_db[cleanName(pilot['name'])] += ' *'
        card_db[cleanName(pilot['name'])] += '\n\r\n'
        if 'ship_override' in pilot:
            card_db[cleanName(pilot['name'])] += '^^Ship: {} ({}/{}/{}/{})'.format(pilot['ship'], pilot['ship_override'].get('attack') or 0, pilot['ship_override']['agility'], pilot['ship_override']['hull'], pilot['ship_override']['shields']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^') + '\n\n'
        else:
            card_db[cleanName(pilot['name'])] += ('^^Ship: {}\n\n'.format(ship_db[pilot['ship']])).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        card_db[cleanName(pilot['name'])] += '^^Skill: {}\n\n^^Points: {}\n\n'.format(pilot['skill'], pilot['points']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if pilot['name'].replace('"','') in pilotTexts:
            card_db[cleanName(pilot['name'])] += ('^^' + pilotTexts[pilot['name'].replace('"','')]['text'] + '\n\n').replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        card_db[cleanName(pilot['name'])] += '\n\n'
        log.info('Added %s', card_db[cleanName(pilot['name'])])

    for upgrade in cards['upgradesById']:
        if not cleanName(upgrade['name']) in card_db:
            card_db[cleanName(upgrade['name'])] = ''
        card_db[cleanName(upgrade['name'])] += '**' + '{}'.format(upgrade['name']) + '**'
        if 'unique' in upgrade:
            card_db[cleanName(upgrade['name'])] += ' *'
        card_db[cleanName(upgrade['name'])] += '\n\r\n'
        if 'faction' in upgrade:
            card_db[cleanName(upgrade['name'])] += '^^Faction: {}\n\n'.format(upgrade['faction']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if 'slot' in upgrade:
            card_db[cleanName(upgrade['name'])] += '^^Type: {}\n\n'.format(upgrade['slot']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if 'attack' in upgrade:
            card_db[cleanName(upgrade['name'])] += '^^Attack: {}\n\n'.format(upgrade['attack']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if 'range' in upgrade:
            card_db[cleanName(upgrade['name'])] += '^^Range: {}\n\n'.format(upgrade['range']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if 'points' in upgrade:
            card_db[cleanName(upgrade['name'])] += '^^Points: {}\n\n'.format(upgrade['points']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if upgrade['name'].replace('"','') in upgradeTexts:
            card_db[cleanName(upgrade['name'])] += ('^^' + upgradeTexts[upgrade['name'].replace('"','')]['text'] + '\n\n').replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        card_db[cleanName(upgrade['name'])] += '\n\n'
        log.info('Added %s', card_db[cleanName(upgrade['name'])])

    for modification in cards['modificationsById']:
        if not cleanName(modification['name']) in card_db:
            card_db[cleanName(modification['name'])] = ''
        card_db[cleanName(modification['name'])] += '**' + '{}'.format(modification['name']) + '**'
        if 'unique' in modification:
            card_db[cleanName(modification['name'])] += ' *'
        card_db[cleanName(modification['name'])] += '\n\r\n'
        if 'ship' in modification:
            card_db[cleanName(modification['name'])] += '^Ship: {}\n\n'.format(modification['ship']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if 'points' in modification:
            card_db[cleanName(modification['name'])] += '^Points: {}\n\n'.format(modification['points']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if modification['name'].replace('"','') in modificationTexts:
            card_db[cleanName(modification['name'])] += ('^^' + modificationTexts[modification['name'].replace('"','')]['text'] + '\n\n').replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        card_db[cleanName(modification['name'])] += '\n\n'
        log.info('Added %s', card_db[cleanName(modification['name'])])

    for titleText in cards['titlesById']:
        if not cleanName(titleText['name']) in card_db:
            card_db[cleanName(titleText['name'])] = ''
        card_db[cleanName(titleText['name'])] += '**' + '{}'.format(titleText['name']) + '**'
        if 'unique' in titleText:
            card_db[cleanName(titleText['name'])] += ' *'
        card_db[cleanName(titleText['name'])] += '\n\r\n'
        if 'ship' in titleText:
            card_db[cleanName(titleText['name'])] += '^Ship: {}\n\n'.format(titleText['ship']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if 'points' in titleText:
            card_db[cleanName(titleText['name'])] += '^Points: {}\n\n'.format(titleText['points']).replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        if titleText['name'].replace('"','') in titleTexts:
            card_db[cleanName(titleText['name'])] += ('^^' + titleTexts[titleText['name'].replace('"','')]['text'] + '\n\n').replace('(','&#40;').replace('(','&#41;').replace(' ',' ^^')
        card_db[cleanName(titleText['name'])] += '\n\n'
        log.info('Added %s', card_db[cleanName(titleText['name'])])

    # Create initialisms
    for upgrade in cards['upgradesById']:
        if len(upgrade['name'].split()) > 1:
            log.info('Adding %s initialism for %s', cleanName(''.join(title[0] for title in upgrade['name'].split())), upgrade['name'])
            initialisms_db[cleanName(''.join(title[0] for title in upgrade['name'].split()))] = card_db[cleanName(upgrade['name'])]

    for modification in cards['modificationsById']:
        if len(modification['name'].split()) > 1:
            log.info('Adding %s initialism for %s', cleanName(''.join(title[0] for title in modification['name'].split())), modification['name'])
            initialisms_db[cleanName(''.join(title[0] for title in modification['name'].split()))] = card_db[cleanName(modification['name'])]

    for titleText in cards['titlesById']:
        if len(titleText['name'].split()) > 1:
            log.info('Adding %s initialism for %s', cleanName(''.join(title[0] for title in titleText['name'].split())), titleText['name'])
            initialisms_db[cleanName(''.join(title[0] for title in titleText['name'].split()))] = card_db[cleanName(titleText['name'])]

    for name, text in initialisms_db.items():
        card_db[name] = text

    return card_db
