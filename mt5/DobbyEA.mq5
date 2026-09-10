#property strict
#property version   "0.1.0"
#property description "Dobby Trade Assistant signal bridge for MetaTrader 5"

input string          ApiUrl          = "http://127.0.0.1:8000/analyze";
input ENUM_TIMEFRAMES AnalysisTimeframe = PERIOD_M15;
input int             LookbackBars    = 100;
input int             RequestTimeoutMs = 5000;
input bool            EnableExecution = false;

datetime last_bar_time = 0;

string TimeframeName()
  {
   return EnumToString(AnalysisTimeframe);
  }

string IsoTimestamp(datetime value)
  {
  string timestamp = TimeToString(value, TIME_DATE | TIME_SECONDS);
  StringReplace(timestamp, " ", "T");
  return timestamp + "Z";
  }

string JsonNumber(double value)
  {
   return DoubleToString(value, _Digits);
  }

string BuildMarketPayload(MqlRates &rates[], int count)
  {
   string json = "{\"symbol\":\"" + _Symbol + "\",\"timeframe\":\"";
   json += TimeframeName() + "\",\"candles\":[";

   bool first = true;
   for(int index = count - 1; index >= 1; index--)
     {
      if(!first)
         json += ",";
      first = false;
      json += "{\"timestamp\":\"" + IsoTimestamp(rates[index].time) + "\"";
      json += ",\"open\":" + JsonNumber(rates[index].open);
      json += ",\"high\":" + JsonNumber(rates[index].high);
      json += ",\"low\":" + JsonNumber(rates[index].low);
      json += ",\"close\":" + JsonNumber(rates[index].close);
      json += ",\"volume\":" + IntegerToString((int)rates[index].tick_volume) + "}";
     }

   json += "],\"account_balance\":" + DoubleToString(AccountInfoDouble(ACCOUNT_BALANCE), 2);
   json += ",\"account_equity\":" + DoubleToString(AccountInfoDouble(ACCOUNT_EQUITY), 2);
   json += ",\"open_orders\":" + IntegerToString(PositionsTotal());
   json += ",\"point\":" + DoubleToString(_Point, _Digits);
   json += ",\"digits\":" + IntegerToString(_Digits) + "}";
   return json;
  }

bool JsonNumberValue(string body, string key, double &value)
  {
   string marker = "\"" + key + "\":";
   int start = StringFind(body, marker);
   if(start < 0)
      return false;

   start += StringLen(marker);
   int finish = StringFind(body, ",", start);
   if(finish < 0)
      finish = StringFind(body, "}", start);
   if(finish < 0)
      return false;

   value = StringToDouble(StringSubstr(body, start, finish - start));
   return true;
  }

string JsonStringValue(string body, string key)
  {
   string marker = "\"" + key + "\":\"";
   int start = StringFind(body, marker);
   if(start < 0)
      return "";

   start += StringLen(marker);
   int finish = StringFind(body, "\"", start);
   if(finish < 0)
      return "";
   return StringSubstr(body, start, finish - start);
  }

bool IsNewBar()
  {
   datetime current = iTime(_Symbol, AnalysisTimeframe, 0);
   if(current == 0 || current == last_bar_time)
      return false;
   last_bar_time = current;
   return true;
  }

void AnalyzeClosedBars()
  {
   MqlRates rates[];
   ArraySetAsSeries(rates, true);
   int requested = MathMax(LookbackBars + 1, 2);
   int copied = CopyRates(_Symbol, AnalysisTimeframe, 0, requested, rates);
   if(copied < 2)
     {
      Print("Dobby EA: not enough bars, copied=", copied);
      return;
     }

   string payload = BuildMarketPayload(rates, copied);
   char request_data[];
   char response_data[];
   string response_headers;
   StringToCharArray(payload, request_data, 0, WHOLE_ARRAY, CP_UTF8);
   ResetLastError();
   int status = WebRequest("POST", ApiUrl, "Content-Type: application/json\r\n", 
                           RequestTimeoutMs, request_data, ArraySize(request_data) - 1,
                           response_data, response_headers);
   if(status == -1)
     {
      Print("Dobby EA: WebRequest failed, error=", GetLastError(),
            ". Add the API host to Tools > Options > Expert Advisors > allowed URLs.");
      return;
     }

   string response = CharArrayToString(response_data, 0, -1, CP_UTF8);
   string action = JsonStringValue(response, "action");
   double entry = 0.0;
   double stop_loss = 0.0;
   double take_profit = 0.0;
   JsonNumberValue(response, "entry", entry);
   JsonNumberValue(response, "stop_loss", stop_loss);
   JsonNumberValue(response, "take_profit", take_profit);

   Print("Dobby EA: HTTP ", status, " action=", action,
         " entry=", DoubleToString(entry, _Digits),
         " sl=", DoubleToString(stop_loss, _Digits),
         " tp=", DoubleToString(take_profit, _Digits));

   if(EnableExecution && action != "WAIT")
      Print("Dobby EA: execution requested but intentionally disabled in this signal-only build.");
  }

int OnInit()
  {
   Print("Dobby EA for MT5 started in signal-only mode");
   return INIT_SUCCEEDED;
  }

void OnTick()
  {
   if(IsNewBar())
      AnalyzeClosedBars();
  }