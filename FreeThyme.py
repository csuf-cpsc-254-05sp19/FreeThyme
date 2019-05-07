import sys, json, flask, flask_socketio, httplib2, uuid
from flask import Response, request, jsonify, session
from flask_socketio import SocketIO
from apiclient import discovery
from oauth2client import client
from googleapiclient import sample_tools
from rfc3339 import rfc3339
from dateutil import parser
from datetime import datetime,date,timedelta,time
import collections


app = flask.Flask(__name__)
socketio = SocketIO(app)
globalSchedule = []


#This is the beginning of the flask route
#PROGRAM STARTS HERE
@app.route('/')
def index():
    #If credentials do not exist, redirect to login page
    if 'credentials' not in flask.session:
        return flask.redirect(flask.url_for('oauth2callback'))
    #Set credentials
    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    #Case if credentials have expired, redirect to login page
    if credentials.access_token_expired:
        return flask.redirect(flask.url_for('oauth2callback'))
    
    try:
        credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    #When credential error
    except credError:
        print("Did not properly assign credentials")
    
    return flask.render_template('thyme-website.html')

#ADD CALENDAR BUTTON RUNS BUT STAYS ON SAME PAGE:
@app.route("/add-calendar", methods=['GET', 'POST'])
def addCalendar():
    if request.method == 'POST':
        _hours = request.form.get('thyme', None)
        _days = request.form.get('search', None)
        session['_hours'] = _hours
        session['_days'] = _days
        print(_hours,_days)
        return flask.redirect(flask.url_for('resultScreen'))
    print("Adding calendar")
    #If credentials do not exist, redirect to login page
    if 'credentials' not in flask.session:
        return flask.redirect(flask.url_for('oauth2callback'))
    #Set credentials
    credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    #Case if credentials have expired, redirect to login page
    if credentials.access_token_expired:
        return flask.redirect(flask.url_for('oauth2callback'))
    try:
        credentials = client.OAuth2Credentials.from_json(flask.session['credentials'])
    #When credential error
    except credError:
        print("Did not properly assign credentials")
    #Create Http authentication
    http_auth = credentials.authorize(httplib2.Http())
    #Create service for Google Calendar API
    service = discovery.build('calendar', 'v3', http_auth)
    page_token = None
    #Create a list of Calendar ID's
    calendarIDs = getCalendarIDs(service, page_token)
    #Run freeBusyQueryFunc
    bigSchedule = freeBusyQueryFunc(calendarIDs, service)
    globalSchedule.extend(bigSchedule) 
    return flask.render_template('thyme-website.html')   
        

#RESET BUTTON RUNS BUT STAYS ON SAME PAGE  
@app.route("/reset-calendar")
def resetCalendar():   
    print("Resetting calendar")
    globalSchedule.clear()
    return flask.render_template('thyme-website.html')
    
@app.route("/thyme-results.html")
def resultScreen():

    bigSchedule = globalSchedule
    #TEMP ASSIGNMENTS
    default_thyme = '3'
    _hours = session.get('_hours', default_thyme)
    default_search = '14'
    try: _days = int(session.get('_days', default_search))
    except: _days = 14

    
    print(_hours,_days)
    
    
    #Add unavailableTimeList to big Schedule
    bigSchedule.extend(unavailableTime(_days))
    
    #Call Function to sort bigSchedule
    _min = convertTimetoMinute(_hours)
    #Make final list by finding time with given minute input
    finalList = findFreeThyme(list(collections.deque(sortSchedule(bigSchedule))), _min)
    '''
    finalList.pop(0)
    finalList.pop()
    finalList = webDisplayFormat(finalList)
    '''
    print(finalList)
    
    return flask.render_template('thyme-results.html')
    
@app.route("/thyme-website-contact.html")
def contactPage():    
    return flask.render_template('thyme-website-contact.html')

@app.route("/thyme-website-about.html")
def aboutPage():    
    return flask.render_template('thyme-website-about.html')


#This is the beginning of the oauth callback route (/login page)
@app.route('/oauth2callback')
def oauth2callback():
    #Call Google OAuth
    flow = client.flow_from_clientsecrets(
        #Load Google Cloud Client ID and Secret
        'client_secrets.json',
        #OAuth Consent Scope (Sensitive Scope)
        scope='https://www.googleapis.com/auth/calendar',
        #Redirect to /login to complete request
        redirect_uri=flask.url_for('oauth2callback', _external=True))
    #Redirect if auth code is not in request
    if 'code' not in flask.request.args:
        auth_uri = flow.step1_get_authorize_url()
        return flask.redirect(auth_uri)
    #Create credentials from auth code
    else:
        auth_code = flask.request.args.get('code')
        credentials = flow.step2_exchange(auth_code)
        flask.session['credentials'] = credentials.to_json()
        
    #Redirect back to index.html
    return flask.redirect(flask.url_for('index'))

#Google Calendar API to collect calendarID's
def getCalendarIDs(service, page_token):
    calendarIDs = []
    while True:
        calendar_list = service.calendarList().list(pageToken=page_token).execute()
        for calendar_list_entry in calendar_list['items']:
            calendarIDs.append({"name": calendar_list_entry['summary'], "id": calendar_list_entry['id']})
        page_token = calendar_list.get('nextPageToken')
        if not page_token:
            break
    return calendarIDs


#Google Calendar API query function
def freeBusyQueryFunc(calendarIDs, service, _days = 14, _timezone = ["America/Los_Angeles","07:00"]):
    bigSchedule = []
    freeBusyQuery = []
    #Query each calendar from list of Calendar ID's
    for x in calendarIDs:
        calID = x.get('id')
        PARAMS = {'timeMin': convertDateTimeToGoogle(datetime.now()),
                  "timeMax": addTimeScan(_days),
                  "timeZone": _timezone[0],
                  "items":[{"id": calID}]
                  }
        
        freeBusyQuery = (service.freebusy().query(body=PARAMS).execute())
        
        #Add all start and end times to bigSchedule
        for elem in freeBusyQuery['calendars'][calID]['busy']:
            bigSchedule.append(elem)
    return bigSchedule

def convertTimetoMinute(timeLength):
    try:
        hours, minutes = timeLength.split(":")
        hours = int(hours)
    except:
        try:
            hours = int(timeLength)
            minutes = 0
        except:
            hours = 3
            minutes = 0
    return(hours*60 + int(minutes))

#Fumction to convert tring to dateTime
def convertDateTime(inputString):
    #parses the first event by "T"
    #so day1 = YEAR-MONTH-DAY, and wholetime = HOUR:MINUTES:SECONDS-TIMEZONE
    date, wholeTime = inputString.split('T')
    
    year, month, day = date.split("-")
    
    #using the whole time we parse it by the "-" symbol meaning that
    #time1 = HOURS:MINUTES:SECONDS, and timezone1 = TIMEZONE
    time, timezone = wholeTime.split("-")
    
    #now that we have the time format as HOUR:MINUTES:SECONDS
    #we can once again parse it to get the HOURs, MINUTEs, and SECONDs 
    #and store them in dedicated variables 
    #hour1 = hours, minutes1 = minutes, seconds1 = seconds, 
    hour, minutes, seconds= time.split(":")
    #we must convert the parsed quantities into integers so that
    #they can be used by the "timedelta" function
    year = int(year)
    month = int(month)
    day = int(day)
    hour = int(hour)
    minute = int(minutes)
    second = int(seconds)
    
    outputDateTime = datetime(year, month, day, hour, minute, second)
    
    return outputDateTime

def convertDateTimeToGoogle(dateTime, _timezone = ["America/Los_Angeles","07:00"]):
    year = dateTime.year
    month = dateTime.month
    day = dateTime.day
    hour = dateTime.hour
    minute = dateTime.minute
    second = dateTime.second
    #Format '2019-05-01T03:00:00-07:00'
    outputString = f"{year:04d}-{month:02d}-{day:02d}T{hour:02d}:{minute:02d}:{second:02d}-{_timezone[1]}"
    
    return str(outputString)

#Function to find difference in time
def findDiffTime(event1, event2):
    
    eventdelta1 = (event1["end"])
    eventdelta2 = (event2["start"])

    lengthOfFreeThyme = eventdelta2 - eventdelta1
    return [lengthOfFreeThyme, event1["end"], event2["start"]]

#Given sorted schedule and minimum appointment length find FreeThyme
def findFreeThyme(eventList, appointmentLength):
    #Format for input eventList, 180 (time in minutes)
    listOfFreeThyme = []
    timeDeltaAppointmentLength = timedelta(minutes = appointmentLength)
    for event1,event2 in zip(eventList, eventList[1:])    :
        freeThyme = findDiffTime(event1,event2)
        if freeThyme[0] >= timeDeltaAppointmentLength:
            listOfFreeThyme.append(freeThyme)
    return listOfFreeThyme
    
    
def addTimeScan(_days,_eHr = 9,_eMin = 00):
    timeDeltaDays = timedelta(days = _days) 
    timeScan = datetime.now() + timeDeltaDays
    timeScan.replace(hour = _eHr)
    timeScan.replace(minute = _eMin)
    timeScan = convertDateTimeToGoogle(timeScan)
    return timeScan
    
    
#Function for to add unavailable time to bigSchedule given start and end time (add this daily)
#Useful to adding bedtimes where it is not a good idea to suggest events in the middle of the night
def unavailableTime(_days,_sHr=0,_sMin=00,_eHr=9,_eMin=00):
    #input an int of days
    unavailableTimeList = []
    for x in range(_days):
       timeDeltaDays = timedelta(days = x) 

       currentDay = datetime.now()

       currentDate = datetime(year = currentDay.year, month = currentDay.month, day=currentDay.day, hour=_sHr, minute=_sMin)
       currentDate = currentDate + timeDeltaDays
       startUn = convertDateTimeToGoogle(currentDate)

       currentDate = datetime(year = currentDay.year, month = currentDay.month, day=currentDay.day, hour=_eHr, minute=_eMin)
       currentDate = currentDate + timeDeltaDays
       endUn = convertDateTimeToGoogle(currentDate)

       unavailableTimeList.append({"start":startUn,"end":endUn})
    return unavailableTimeList

def sortSchedule(bigSchedule):
    startTimeList = []
    endTimeList = []
    print(bigSchedule)
    for x in bigSchedule:
        startTimeList.append(convertDateTime(x["start"]))
        endTimeList.append(convertDateTime(x["end"]))
    print(startTimeList)
    print(endTimeList)
    startTimeList.sort()
    endTimeList.sort()
    outputList = []
    for x in startTimeList:
        tempDict = {"start":x,"end":endTimeList[startTimeList.index(x)]}
        print(tempDict)
        outputList.append(tempDict)
    return outputList
        
    

'''
#OLD SORT FUNCTION
def sortSchedule(bigSchedule):
    sortedSchedule = collections.deque([])
    #Convert bigSchedule to sortedSchedule
    for event in bigSchedule:
        #If sortedSchedule deque is empty, append first element
        if not sortedSchedule:
            sortedSchedule.append(event)
        #Else if startTime[0] is less than startTime of element and endTime is less than startTime of element
        elif convertDateTime(event['end']) < convertDateTime(sortedSchedule[0]['start']):
            #Append the event to the front of sortedSchedule
            sortedSchedule.appendleft(event)
        #Else if endTime[-1] (Right most element) is less than the start of of event
        elif convertDateTime(sortedSchedule[-1]['end']) < convertDateTime(event['start']):
            #Append the event to the back of sortedSchedule
            sortedSchedule.append(event)
        #Non empty deque and if element is not able to be appended to front or back
        else:
            for sortedEvents in sortedSchedule:
                #If event end is less than startTime element and start is greater than endTime previous of element
                if convertDateTime(event['end']) <= convertDateTime(sortedEvents['start']) and convertDateTime(event['start']) > convertDateTime(sortedSchedule[sortedEvents-1]['end']):
                    #Insert element into that location
                    sortedSchedule.insert(sortedEvents, event)
                    break
                #Else if event startTime is less than current sortedEvent startTime and event endTime is less than current sortedEvent endTime
                elif convertDateTime(event['start']) < convertDateTime(sortedEvents['start']) and convertDateTime(event['end']) <= convertDateTime(sortedEvents['end']):
                    #Replace current sortedEvent startTime with event startTime value
                    sortedEvents['start'] = event['start']
                    break
                #Else if event endTime is greater than current sortedEvent endTime and event startTime is greater than current sortedEvent startTime
                elif convertDateTime(event['end']) > convertDateTime(sortedEvents['end']) and convertDateTime(event['start']) >= convertDateTime(sortedEvents['start']):
                    sortedEvents['end'] = event['end']
                    #Replace current sortedEvent endTime with event endTime value
                    break
                #Else: event is already part of a sortedEvent
                #event endTime is less than current sortedEvent endTime and event startTime is greater than current sortedEvent startTime
                elif convertDateTime(event['end']) <= convertDateTime(sortedEvents['end']) and convertDateTime(event['start']) >= convertDateTime(sortedEvents['start']):
                    break
                else:
                    pass
    return sortedSchedule
'''
    
def webDisplayFormat(finalList):
    revisedFinalList = []
    for freeThyme in finalList:
        #creates a larger list to store the "freethyme events"

        displayList = []
        displayList.append(freeThyme[0])

        #converts numDay to wordDay
        date1, wholeTime1 = freeThyme[1].split('T')
        year, month, day = date1.split('-')
        year = int(year)
        month = int(month)
        day = int(day)
        stringDate = date(year,month,day).strftime("%A, %B %d, %Y   ~   ")
        displayList.append(stringDate)

        #creates startTime by parsing
        fullTime1, timeZone = wholeTime1.split("-")
        hours, minutes, seconds = fullTime1.split(":")
        hours = int(hours)
        minutes = int(minutes)
        startTime = time(hour=hours,minute=minutes).strftime("%I:%M %p")

        #creates entTime by parsing
        date2, wholeTime2 = freeThyme[2].split('T')
        fullTime2, timeZone = wholeTime2.split("-")
        hours, minutes, seconds = fullTime2.split(":")
        hours = int(hours)
        minutes = int(minutes)
        endTime = time(hour=hours,minute=minutes).strftime("%I:%M %p")

        #creates time interval
        timeInterval =  startTime + " - " + endTime

        #appends the time interval for list
        displayList.append(timeInterval)

        #adds "freethyme event" into bigger list of "freethyme events"
        revisedFinalList.append(displayList)
    return revisedFinalList

#Server setup
if __name__ == '__main__':
    app.secret_key = str(uuid.uuid4())
    print('Server starting...')
    socketio.run(
    app,
    host='localhost',
    port=int(8080),
    )

