#!/opt/local/bin/python2.6

import sys
import sqlite3
import string
from datetime import time, date, datetime
import wx
app = wx.App(redirect = 0)
from xml.sax.saxutils import quoteattr
import re

DATABASE_FILE = "ticketdb"
XML_LOG_FILE = "ticket-transactions-%s.xml" % datetime.now().strftime("%Y-%m-%d")
EXIT_PASSWORD = "password"

ACCEPT_SOUND = "burn_scan/accept.wav"
REJECT_SOUND = "burn_scan/reject.wav"

DOCTEXT="Use (b) to scan barcodes for entry. When you have a new greeter shift change, select Change Greeter (g) to specify the name of the new greeter.  Use the information panel (i) to scan to see if a barcode is valid without using it, or to see a breakdown of entrance counts."

MODE_ENTER = 1
MODE_INFO = 2
MODE_EXIT = 3

OK_TICKET_COLOR = (128, 255, 128)
BAD_TICKET_COLOR = (255, 96, 96)
INFO_COLOR = (255, 255, 255)
EXIT_COLOR = (255, 255, 128)

class ticketmainwindow(wx.Frame):
    def ChangeGreeter(self, event=None):
        dlg = wx.TextEntryDialog(self, 'What is your name, greeter?','Greeter Name')
        dlg.SetValue("")
        if dlg.ShowModal() == wx.ID_OK:
            self.CurrentGreeter = dlg.GetValue()
            self.SetModeEnter()
        dlg.Destroy()

    def SetModeEnter(self, event=None):
        self.CurrentMode = MODE_ENTER
        self.UpdateModeButtons()
        self.ActionResults.SetBackgroundColour(OK_TICKET_COLOR)
        if self.ValidGreeter():
            self.ActionResults.SetValue("Hello, " + self.CurrentGreeter + "!  Scan barcode for entry.")
        else:
            self.ActionResults.SetValue("You have not yet entered a valid greeter name.")

    def SetModeInfo(self, event=None):
        self.CurrentMode = MODE_INFO
        self.UpdateModeButtons()
        self.ActionResults.SetBackgroundColour(INFO_COLOR)
        self.ActionResults.SetValue("")

        self.ActionBoxSizer.Show(self.InfoTree, True)
        self.ActionBoxSizer.Layout()

        self.InfoTree.DeleteChildren(self.InfoTreeRoot)

        cursor2 = self.sqlconn.cursor()
        self.cursor.execute('select tier_id, label from tier order by tier_id')
        for tier in self.cursor:
            cursor2.execute('select count(*) as tot, count(entry_at) as entered from ticket where tier_id = ?', (tier['tier_id'],))
            (tier_entered, tier_total, tier_entered_today) = (0, 0, 0)
            for entered in cursor2:
                tier_entered = entered['entered']
                tier_total = entered['tot']
            cursor2.execute('select count(*) as today from ticket where tier_id = ? and entry_at > date()', (tier['tier_id'],))
            for entered in cursor2:
                tier_entered_today = entered['today']
            label = "%s: %d/%d checked in" % (tier['label'], tier_entered, tier_total)
            if tier_entered_today > 0:
                label += " (%d today)" % tier_entered_today
            newitem = self.InfoTree.AppendItem(self.InfoTreeRoot, label)
            self.InfoTree.SetItemPyData(newitem, ("tier", tier['tier_id']))
            if tier_total > 0:
                self.InfoTree.SetItemHasChildren(newitem, True)

    def InfoTreeExpanding(self, event):
        tier_item = event.GetItem()
        if tier_item == self.InfoTreeRoot:
            event.Skip()
            return
        self.InfoTree.DeleteChildren(tier_item)
        (data_type, data_value) = self.InfoTree.GetItemPyData(tier_item)
        if data_type != 'tier': return
        self.cursor.execute('select barcode, number, assigned_name, entry_at from ticket where tier_id = ? order by entry_at desc, assigned_name, number', (data_value,))
        for row in self.cursor:
            message = '%s: %s (#%d)' % (row['barcode'], row['assigned_name'], row['number'])
            if row['entry_at']:
                message += ' entered at: ' + row['entry_at']
            newitem = self.InfoTree.AppendItem(tier_item, message)
            self.InfoTree.SetItemPyData(newitem, ("barcode", row['barcode']))
        event.Skip()


    def InfoTreeActivated(self, event):
        selected_item = event.GetItem()
        (data_type, barcode) = self.InfoTree.GetItemPyData(selected_item)
        if data_type == 'barcode':
            self.ShowBarcode(barcode, mode = MODE_INFO)

    def SetModeExit(self, event=None):
        dlg = wx.TextEntryDialog(self, 'Enter password for access to scan-out','Password', style = wx.TE_PASSWORD | wx.OK | wx.CANCEL | wx.CENTRE)
        dlg.SetValue("")
        if dlg.ShowModal() == wx.ID_OK:
            if dlg.GetValue() == EXIT_PASSWORD:
                self.CurrentMode = MODE_EXIT
                self.UpdateModeButtons()
                self.ActionResults.SetBackgroundColour(EXIT_COLOR)
                self.ActionResults.SetValue("Scan barcode to check user out of event")
            else:
                dlg.Destroy()
                dlg = wx.MessageDialog(self, 'The password you entered was invalid.', 'Bad password', style = wx.OK | wx.ICON_INFORMATION)
                dlg.ShowModal()

        dlg.Destroy()

    def UpdateModeButtons(self):
        self.ActionBoxSizer.Show(self.InfoTree, False)
        self.ActionBoxSizer.Layout()

        self.EnterEventButton.SetValue(self.CurrentMode == MODE_ENTER)
        self.InfoButton.SetValue(self.CurrentMode == MODE_INFO)
        self.ExitEventButton.SetValue(self.CurrentMode == MODE_EXIT)
        self.BarcodeEntry.SetValue('')

    def OnBarcodeChar(self, event):
        keycode = event.GetKeyCode()
        if keycode == ord('e'):
            self.SetModeEnter()
            return
        if keycode == ord('i'):
            self.SetModeInfo()
            return
        if keycode == ord('x'):
            self.SetModeExit()
            return
        if keycode == ord('g'):
            self.ChangeGreeter()
            return
        if keycode == ord('b'):
            # barcode entry; sent by reader (along with the control key presumably) before the barcode
            self.BarcodeEntry.SetFocus()
            self.BarcodeEntry.SelectAll()
            return

        if keycode == wx.WXK_RETURN or keycode == ord('c'):
            # barcode entry finished; "c" is sent sent by reader (along with the control key presumably) after the barcode
            barcode = self.BarcodeEntry.GetValue()
            self.ShowBarcode(barcode, mode = (self.CurrentMode))
            self.BarcodeEntry.SelectAll()
        elif (keycode >= ord('0') and keycode <= ord('9')) or keycode > 255 or not (chr(keycode) in string.printable):
            # regular digit or cursor movement key. pass to textctrl
            event.Skip()

    def ShowBarcode(self, barcode, mode = MODE_INFO):
        self.cursor.execute('select barcode, tier_id, code, number, user_email, assigned_name, purchase_date, entry_at from ticket where barcode = ?', (barcode,))
        valid_barcode = False
        for row in self.cursor:
            valid_barcode = True
        
        if not valid_barcode:
            self.ActionResults.SetValue('Invalid ticket barcode: ' + barcode)
            if mode == MODE_INFO:
                self.ActionResults.SetBackgroundColour(INFO_COLOR)
            else:
                self.ActionResults.SetBackgroundColour(BAD_TICKET_COLOR)
                wx.Sound.PlaySound(REJECT_SOUND)
            return
        
        message = '''
Barcode: %s
Tier code: %s
Ticket Code: %s
Ticket Number: %s
Email: %s
Name: %s
Purchase date: %s
''' % (row['barcode'], row['tier_id'], row['code'], row['number'], row['user_email'], row['assigned_name'], row['purchase_date'])

        if mode == MODE_ENTER:
            if row['entry_at']:
                message = "Ticket already used.\n" + message + "Entered event at: " + row['entry_at']
                self.LogTicket(barcode, "reject", "Attempted entry; ticket already used")
                self.ActionResults.SetBackgroundColour(BAD_TICKET_COLOR)
                wx.Sound.PlaySound(REJECT_SOUND)
            else:
                message = "Ticket valid for entry.\n" + message
                self.cursor.execute('update ticket set entry_at = datetime() where barcode = ?', (barcode,))
                self.tickets_entered = self.tickets_entered + 1
                self.tickets_entered_today = self.tickets_entered_today + 1
                self.LogTicket(barcode, "enter", "Ticket used for entry")
                self.ActionResults.SetBackgroundColour(OK_TICKET_COLOR)
                wx.Sound.PlaySound(ACCEPT_SOUND)
        if mode == MODE_EXIT:
            if row['entry_at']:
                message = message + "Entered event at: " + row['entry_at']
                self.cursor.execute('update ticket set entry_at = null where barcode = ?', (barcode,))
                self.LogTicket(barcode, "exit", "Exiting event")
                self.ActionResults.SetBackgroundColour(OK_TICKET_COLOR)
                self.__update_ticket_counts()
            else:
                message = "Ticket not registered as entered.\n" + message
                self.LogTicket(barcode, "reject-exit", "Scanned for exit; ticket not registered as entered")
                self.ActionResults.SetBackgroundColour(BAD_TICKET_COLOR)
        if mode == MODE_INFO:
            if row['entry_at']:
                message = message + "Entered event at: " + row['entry_at'] + "\n"
                self.ActionResults.SetBackgroundColour(INFO_COLOR)
            else:
                self.ActionResults.SetBackgroundColour(INFO_COLOR)

        message += '''
History:
'''
        self.cursor.execute('select barcode, greeter, message, message_at from ticketlog where barcode = ? order by message_at desc',
                            (barcode,))
        for row in self.cursor:
            message += row['message_at'] + " (" + row['greeter'] + "): " + row['message'] + "\n"
    
        self.ActionResults.SetValue(message)

    def LogTicket(self, barcode, transtype, message):
        self.cursor.execute('insert into ticketlog (barcode, greeter, message, message_at) values (?, ?, ?, datetime())', (barcode, self.CurrentGreeter, message))
        self.sqlconn.commit()
        
        f = open(XML_LOG_FILE, 'a')
        f.write("<" + transtype + " greeter=" + quoteattr(self.CurrentGreeter) + " barcode=" + quoteattr(barcode) + " timestamp=" + quoteattr(datetime.now().strftime("%Y-%m-%d %H:%M:%S")) + ">\n  " + message + "\n<" + transtype + ">\n")
        f.close()

    def __init__(self,parent,id,title,**kwds):
        self.title = title
        self.CurrentGreeter = None
        self.updating_greeter = False
        
        wx.Frame.__init__(self,parent,id,title,**kwds)

        font = wx.SystemSettings_GetFont(wx.SYS_SYSTEM_FONT)
        font.SetPointSize(20)
        self.ReadableFont = font
        
        self.BarcodeEntry = wx.TextCtrl(self, -1, style = wx.WANTS_CHARS)
        self.SummaryText = wx.StaticText(self, -1, "Greeter: ? Tickets used: ?/?")
        self.SummaryText.SetFont(self.ReadableFont)
        self.ActionResults = wx.TextCtrl(self, -1, style = wx.TE_READONLY | wx.TE_MULTILINE)
        self.ActionResults.SetBackgroundStyle(wx.BG_STYLE_COLOUR)
        self.ActionResults.SetBackgroundColour(INFO_COLOR)
        self.ActionResults.SetFont(self.ReadableFont)
        self.InfoTree = wx.TreeCtrl(self, style=wx.TR_HIDE_ROOT | wx.TR_HAS_BUTTONS | wx.TR_DEFAULT_STYLE)
        self.InfoTreeRoot = self.InfoTree.AddRoot('Tiers')
        # self.InfoTree.Expand(self.InfoTreeRoot)
        self.Bind(wx.EVT_TREE_ITEM_EXPANDING, self.InfoTreeExpanding, self.InfoTree)
        self.Bind(wx.EVT_TREE_ITEM_ACTIVATED, self.InfoTreeActivated, self.InfoTree)

        self.__do_layout()
        self.__open_database()
        self.SetModeEnter()

        # update our current time and counts every second:
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.UpdateSummary, self.timer)
        self.timer.Start(500)

    
    def __do_layout(self):
        barcoderow = wx.BoxSizer(wx.HORIZONTAL)
        barcodetext = wx.StaticText(self, -1, "Barcode:")
        barcodeentry = self.BarcodeEntry
        barcoderow.Add(barcodetext, proportion=0, flag = wx.EXPAND)
        barcoderow.Add(barcodeentry, proportion=1, flag = wx.LEFT, border = 5)
        
        actionrow = wx.BoxSizer(wx.HORIZONTAL)
        self.EnterEventButton = wx.ToggleButton(self, -1, "Scan for entry (e)")
        self.InfoButton = wx.ToggleButton(self, -1, "Information (i)")
        self.ExitEventButton = wx.ToggleButton(self, -1, "Scan for exit (x)")
        self.ChangeGreeterButton = wx.Button(self, -1, "Change greeter (g)")
        self.EnterEventButton.SetFont(self.ReadableFont)
        self.InfoButton.SetFont(self.ReadableFont)
        self.ExitEventButton.SetFont(self.ReadableFont)
        self.ChangeGreeterButton.SetFont(self.ReadableFont)
        actionrow.Add(self.EnterEventButton, proportion = 1, flag = wx.EXPAND | wx.LEFT | wx.RIGHT, border = 5)
        actionrow.Add(self.InfoButton, proportion = 1, flag = wx.EXPAND | wx.LEFT | wx.RIGHT, border = 5)
        actionrow.Add(self.ExitEventButton, proportion = 1, flag = wx.EXPAND | wx.LEFT | wx.RIGHT, border = 5)
        actionrow.Add(self.ChangeGreeterButton, proportion = 1, flag = wx.EXPAND | wx.LEFT | wx.RIGHT, border = 5)

        self.BarcodeEntry.Bind(wx.EVT_CHAR, self.OnBarcodeChar)

        self.EnterEventButton.Bind(wx.EVT_TOGGLEBUTTON, self.SetModeEnter)
        self.InfoButton.Bind(wx.EVT_TOGGLEBUTTON, self.SetModeInfo)
        self.ExitEventButton.Bind(wx.EVT_TOGGLEBUTTON, self.SetModeExit)
        self.ChangeGreeterButton.Bind(wx.EVT_BUTTON, self.ChangeGreeter)
        
        self.ActionBoxSizer = wx.BoxSizer(wx.HORIZONTAL)
        self.ActionBoxSizer.Add(self.InfoTree, proportion=1, flag = wx.EXPAND)
        self.ActionBoxSizer.Add(self.ActionResults, proportion=1, flag = wx.EXPAND)

        doc = wx.TextCtrl(self, -1, DOCTEXT, style = wx.TE_READONLY | wx.TE_MULTILINE)
        doc.SetFont(self.ReadableFont)
        sizer = wx.BoxSizer(wx.VERTICAL)
        sizer.Add(barcoderow, proportion = 0, flag = wx.EXPAND | wx.LEFT | wx.RIGHT | wx.TOP, border = 5)
        sizer.Add(self.SummaryText, proportion = 0, flag = wx.EXPAND | wx.ALL, border = 5)
        sizer.Add(actionrow, proportion = 0, flag = wx.EXPAND | wx.LEFT | wx.BOTTOM | wx.RIGHT, border = 5)
        sizer.Add(doc, proportion = 0, flag = wx.EXPAND | wx.LEFT |wx.RIGHT, border = 5)
        sizer.Add(self.ActionBoxSizer, proportion = 1, flag = wx.EXPAND | wx.LEFT | wx.BOTTOM | wx.RIGHT, border=5)
        
        #sizer.Fit(self)
        #self.SetAutoLayout(1)
        #self.SetSizer(sizer)
        #sizer.Fit(self)
        self.SetSizer(sizer)
        self.Maximize(True)

    def __open_database(self):
        self.sqlconn = sqlite3.connect("ticketdb")
        self.sqlconn.row_factory = sqlite3.Row
        self.cursor = self.sqlconn.cursor()

        self.__update_ticket_counts()

    def __update_ticket_counts(self):
        self.cursor.execute('select count(*), count(entry_at) from ticket')
        self.tickets_total = 0
        self.tickets_entered = 0
        for row in self.cursor:
            (self.tickets_total, self.tickets_entered) = row

        self.cursor.execute('select count(*) from ticket where entry_at > date()')
        self.tickets_entered_today = 0
        for row in self.cursor:
            (self.tickets_entered_today,) = row

    def UpdateSummary(self, event=None):
        self.SummaryText.SetLabel('Tickets used today: %d  Tickets used total:  %d of %d  Current greeter: %s  Current time: %s' %
                                  (self.tickets_entered_today, self.tickets_entered,
                                   self.tickets_total,
                                   self.CurrentGreeter,
                                   datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        if not self.updating_greeter:
            if (not self.ValidGreeter()) and (not self.updating_greeter):
                self.updating_greeter = True
                self.ChangeGreeter()
                self.updating_greeter = False
            self.BarcodeEntry.SetFocus()

    def ValidGreeter(self):
        if self.CurrentGreeter is None: return False
        if len(self.CurrentGreeter) < 2: return False
        if re.search("[0-9]+", self.CurrentGreeter):
            # looks like we got a barcode in our greeter name
            return False
        return True


# style = wx.MAXIMIZE,  - only works under gtk+ and windows, not w/ carbon
frame = ticketmainwindow(None, -1, 'ticketui.py')

frame.Show()
app.MainLoop()




