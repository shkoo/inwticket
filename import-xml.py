#!/usr/bin/python

from xml.dom.minidom import parse
import sqlite3
import os
from datetime import datetime, time

def fromxmldate(datestr):
    # parse "Feb. 27, 2011, 4:33 a.m." into something a bit more usable
    datestr = datestr.replace("a.m.","AM")
    datestr = datestr.replace("p.m.","PM")
    newdate = datetime.strptime(datestr, "%b. %d, %Y, %I:%M %p")
    # print datestr, " -> ", newdate.isoformat()
    return newdate

os.remove("ticketdb")
ticketxml = parse("burn_scan/brt_ticket_export.xml")
sqlconn = sqlite3.connect("ticketdb")
cursor = sqlconn.cursor()
cursor.execute('''
create table tier (
   tier_id char(1) not null,
   label varchar(50) not null,
   primary key (tier_id)
)
''')

cursor.execute('''
create table ticket (
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
create table ticketlog (
  barcode varchar(100) not null,
  greeter varchar(100) not null,
  message text,
  message_at datetime not null)
''')

cursor.execute('''
create index ticketlogidx on ticketlog (barcode)
''')


tiers = ticketxml.getElementsByTagName("tier")
for tier in tiers:
    if tier.tagName != "tier": continue
    tier_id = tier.getAttribute("code")
    for tiernode in tier.childNodes:
        if tiernode.nodeName == "label":
            cursor.execute("insert into tier (tier_id, label) values (?, ?)", (tier_id, tiernode.childNodes[0].wholeText))
        if tiernode.nodeName != "tickets":
            continue

        for ticket in tiernode.childNodes:
            if ticket.nodeName != "ticket": continue
            number = ticket.getAttribute("number")
            attribs = dict()
            for ticketnode in ticket.childNodes:
                if ticketnode.nodeType != ticketnode.ELEMENT_NODE: continue
                attribs[ticketnode.nodeName] = ticketnode.childNodes[0].wholeText
            barcode = "%s%05i%s" % (tier_id, int(number), attribs["code"])
            
            cursor.execute('''
insert into ticket (barcode, tier_id, code, number, user_email, assigned_name, purchase_date, used_at, is_present)
values (?, ?, ?, ?, ?, ?, ?, null, 0)''',
                           (barcode, tier_id, attribs["code"], number, attribs["user_email"], attribs["assigned_name"], fromxmldate(attribs["purchase_date"])))

sqlconn.commit()
sqlconn.close()



