#!/opt/local/bin/python2.6

TICKET_XML_URL=None
TICKET_XML_FILE=None

from xml.dom.minidom import parse
import urllib
import sqlite3
import os
from datetime import datetime, time

def fromxmldate(datestr):
    try:
        # parse "Feb. 27, 2011, 4:33 a.m." into something a bit more usable
        newdatestr = datestr.replace("a.m.","AM")
        newdatestr = datestr.replace("p.m.","PM")
        newdate = datetime.strptime(newdatestr, "%b. %d, %Y, %I:%M %p")
        return newdate
    except ValueError:
        # not this format; try a different format
        pass

    # parse "2011-03-01T10:03:20Z"
    newdate = datetime.strptime(datestr, "%Y-%m-%dT%H:%M:%SZ")
    return newdate

def setupdb():
    sqlconn = sqlite3.connect("ticketdb")
    cursor = sqlconn.cursor()

    cursor.execute('''
    create table if not exists tier (
       tier_id char(1) not null,
       label varchar(50) not null,
       primary key (tier_id)
    )
    ''')

    cursor.execute('''
    create table if not exists  ticket (
       barcode varchar(100) not null,
       tier_id char(1) not null,
       code int not null,
       number int not null,
       user_email varchar(100),
       assigned_name varchar(100),
       purchase_date datetime,
       used_at datetime,
       is_present int(1) not null,   
       primary key(barcode)
    )
    ''')

    cursor.execute('''
    create table if not exists ticketlog (
      barcode varchar(100) not null,
      greeter varchar(100) not null,
      message text,
      message_at datetime not null)
    ''')

    cursor.execute('''
    create index if not exists ticketlogidx on ticketlog (barcode)
    ''')

    sqlconn.commit()
    sqlconn.close()


def importxml():

    if TICKET_XML_URL:
        urlreader = urllib.urlopen(TICKET_XML_URL)
        ticketxml = parse(urlreader)
    else:
        ticketxml = parse(TICKET_XML_FILE)

    sqlconn = sqlite3.connect("ticketdb")
    cursor = sqlconn.cursor()

    tiers = ticketxml.getElementsByTagName("tier")
    for tier in tiers:
        if tier.tagName != "tier": continue
        tier_id = tier.getAttribute("code")
        for tiernode in tier.childNodes:
            if tiernode.nodeName == "label":
                cursor.execute("insert or ignore into tier (tier_id, label) values (?, ?)", (tier_id, tiernode.childNodes[0].wholeText))
            if tiernode.nodeName != "tickets":
                continue

            for ticket in tiernode.childNodes:
                if ticket.nodeName != "ticket": continue
                number = ticket.getAttribute("number")
                attribs = dict()
                for ticketnode in ticket.childNodes:
                    if ticketnode.nodeType != ticketnode.ELEMENT_NODE: continue
                    if ticketnode.childNodes:
                        attribs[ticketnode.nodeName] = ticketnode.childNodes[0].wholeText
                    else:
                        attribs[ticketnode.nodeName] = ""
                barcode = "%s%05i%s" % (tier_id, int(number), attribs["code"])

                cursor.execute('''
    insert or ignore into ticket (barcode, tier_id, code, number, user_email, assigned_name, purchase_date, used_at, is_present)
    values (?, ?, ?, ?, ?, ?, ?, null, 0)''',
                               (barcode, tier_id, attribs["code"], number, attribs["user_email"], attribs["assigned_name"], fromxmldate(attribs["purchase_date"])))


    sqlconn.commit()
    sqlconn.close()


if __name__ == "__main__":
    setupdb()
    importxml()
