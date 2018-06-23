import json
import time
import webapp2
import urllib
from google.appengine.api import urlfetch
from google.appengine.api import memcache

FORM = """
<html>
<body>
<form action="/submit">
  City: <input type="text" name="city"><br>
  Checkin: <input type="text" name="checkin"><br>
  Checkout: <input type="text" name="checkout"><br>
  <input type="submit" value="Submit">
</form> 
</body>
</html>
"""

class MainPage(webapp2.RequestHandler):
    def get(self):
        self.response.write(FORM)

class SubmitPage(webapp2.RequestHandler):

    CACHE_TTL = 60  # seconds

    def CacheKey(self):
      return 'city:%scheckin:%scheckout%s' % (self.request.get('city'), self.request.get('checkin'), self.request.get('checkout'))

    def Cache(self, response):
      memcache.add(self.CacheKey(), response, self.CACHE_TTL)

    def GetFromCache(self):
      return memcache.get(self.CacheKey())

    def SendPostRequest(self, provider):
      payload = urllib.urlencode({
            'city' : self.request.get('city'),
            'checkin' : self.request.get('checkin'),
            'checkout' : self.request.get('checkout'),
            'provider' : provider,
        })
      rpc = urlfetch.create_rpc()
      urlfetch.make_fetch_call(rpc, 'https://experimentation.getsnaptravel.com/interview/hotels', payload, urlfetch.POST)
      return rpc

    def GetHotelByName(self, fetch_rpc):
      hotel_list = json.loads(fetch_rpc.get_result().content)['hotels']
      return {entry['hotel_name']: entry for entry in hotel_list}

    def get(self):
        cached_response = self.GetFromCache()
        if cached_response:
          self.response.write(cached_response)
          return

        snap_rates_rpc = self.SendPostRequest('snaptravel')
        hotel_com_rates_rpc = self.SendPostRequest('retail')

        snap_rates_rpc.wait()
        hotel_com_rates_rpc.wait()

        snap_hotel_by_name = self.GetHotelByName(snap_rates_rpc)
        hotel_com_by_name = self.GetHotelByName(hotel_com_rates_rpc)

        same_hotels = set(snap_hotel_by_name).intersection(set(hotel_com_by_name))

        if not same_hotels:
          self.response.write("No matching hotels")

        columns = [column for column in snap_hotel_by_name[next(iter(same_hotels))].keys() if column not in ['hotel_name', 'price']]

        columns_html = '<tr><th>hotel_name</th>'
        for column in columns:
          columns_html += '<th>%s</th>' % column
        columns_html += '<th>%s</th><th>%s</th></tr>' % ('Snaptravel Price', 'Hotels.com Price')

        rows_html = ''
        for hotel_name in same_hotels:
          row_html = '<tr><td>%s</td>' % hotel_name
          for column in columns:
            data = snap_hotel_by_name[hotel_name][column]
            if column == 'image_url':
              data = '<img src="%s">' % data
            row_html += '<td>%s</td>' % data
          row_html += '<td>%s</td><td>%s</td></tr>' % (snap_hotel_by_name[hotel_name]['price'], hotel_com_by_name[hotel_name]['price'])
          rows_html += row_html

        response = '<table>%s%s</table>' % (columns_html, rows_html)
        self.Cache(response)
        self.response.write(response)


app = webapp2.WSGIApplication([
    ('/', MainPage),
    ('/submit', SubmitPage),
], debug=True)
