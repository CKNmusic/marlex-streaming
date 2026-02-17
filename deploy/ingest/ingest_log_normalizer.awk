BEGIN {
  app_name = ENVIRON["APP_NAME"]
  app_version = ENVIRON["APP_VERSION"]
  if (app_name == "") app_name = "surgwaze"
  if (app_version == "") app_version = "v1"
}

{
  raw_line = $0
  timestamp = ""
  key = "-"
  conn = ""

  if (raw_line ~ /^[0-9][0-9][0-9][0-9]\/[0-9][0-9]\/[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9]/) {
    timestamp = substr(raw_line, 1, 19)
  } else {
    timestamp = strftime("%Y/%m/%d %H:%M:%S", systime())
  }

  if (match(raw_line, /\[conn [^]]+\]/)) {
    conn_tag = substr(raw_line, RSTART, RLENGTH)
    gsub(/^\[conn /, "", conn_tag)
    gsub(/\]$/, "", conn_tag)
    conn = conn_tag
  }

  key_prefix = app_name "/" app_version "/"
  key_start = index(raw_line, key_prefix)
  if (key_start > 0) {
    key_source = substr(raw_line, key_start + length(key_prefix))
    key_end = index(key_source, "/stream")
    if (key_end > 1) {
      key = substr(key_source, 1, key_end - 1)
      gsub(/[^A-Za-z0-9]/, "", key)
      if (key == "") {
        key = "-"
      } else {
        key = toupper(key)
      }
    }
  }

  if (key == "-" && conn != "" && conn in conn_key) {
    key = conn_key[conn]
  }
  if (key != "-" && conn != "" && raw_line ~ /is publishing to path/) {
    conn_key[conn] = key
  }

  if (raw_line ~ /^[0-9][0-9][0-9][0-9]\/[0-9][0-9]\/[0-9][0-9] [0-9][0-9]:[0-9][0-9]:[0-9][0-9] /) {
    raw_line = substr(raw_line, 21)
  }
  printf "%s | %s | %s\n", timestamp, key, raw_line
  fflush()

  if (conn != "" && raw_line ~ /closed:/) {
    delete conn_key[conn]
  }
}
