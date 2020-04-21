//
// Created by Keren Dong on 2020/3/27.
//

#include <kungfu/yijinjing/index/session.h>

using namespace sqlite_orm;
using namespace kungfu::longfist;
using namespace kungfu::longfist::enums;
using namespace kungfu::longfist::types;
using namespace kungfu::yijinjing;
using namespace kungfu::yijinjing::cache;
using namespace kungfu::yijinjing::data;
using namespace kungfu::yijinjing::journal;

namespace kungfu::yijinjing::index {
std::string get_index_db_file(const io_device_ptr &io_device) {
  auto locator = io_device->get_locator();
  auto index_location = location::make_shared(mode::LIVE, category::SYSTEM, "journal", "index", locator);
  return locator->layout_file(index_location, layout::SQLITE, "index");
}

session_finder::session_finder(const io_device_ptr &io_device)
    : session_storage_(cache::make_storage(get_index_db_file(io_device), longfist::SessionDataTypes)),
      io_device_(io_device) {
  if (not session_storage_.sync_schema_simulate().empty()) {
    session_storage_.sync_schema();
  }
}

session_finder::~session_finder() { io_device_.reset(); }

int64_t session_finder::find_last_active_time(const data::location_ptr &source_location) {
  auto sessions = session_storage_.get_all<Session>(where(eq(&Session::location_uid, source_location->uid)),
                                                    order_by(&Session::begin_time).desc(), limit(1));
  return sessions.empty() ? INT64_MAX : sessions.front().end_time;
}

SessionVector session_finder::find_sessions(int64_t from, int64_t to) {
  auto bt = &Session::begin_time;
  return session_storage_.get_all<Session>(where(greater_or_equal(bt, from) and lesser_or_equal(bt, to)), order_by(bt));
}

SessionVector session_finder::find_sessions_for(const location_ptr &source_location, int64_t from, int64_t to) {
  auto bt = &Session::begin_time;
  return session_storage_.get_all<Session>(order_by(bt), where(eq(&Session::location_uid, source_location->uid) and
                                                               greater_or_equal(bt, from) and lesser_or_equal(bt, to)));
}

session_builder::session_builder(const io_device_ptr &io_device) : session_finder(io_device) {
  if (not session_storage_.sync_schema_simulate().empty()) {
    session_storage_.sync_schema();
  }
}

int64_t session_builder::find_last_active_time(const data::location_ptr &source_location) {
  return session_finder::find_last_active_time(source_location);
}

Session &session_builder::open_session(const location_ptr &source_location, int64_t time) {
  if (live_sessions_.find(source_location->uid) == live_sessions_.end()) {
    Session session = {};
    session.location_uid = source_location->uid;
    session.category = source_location->category;
    session.group = source_location->group;
    session.name = source_location->name;
    session.mode = source_location->mode;
    live_sessions_.emplace(session.location_uid, session);
  }
  Session &session = live_sessions_.at(source_location->uid);
  session.begin_time = time;
  session_storage_.replace(session);
  return session;
}

void session_builder::close_session(const location_ptr &source_location, int64_t time) {
  if (live_sessions_.find(source_location->uid) == live_sessions_.end()) {
    return;
  }
  Session &session = live_sessions_.at(source_location->uid);
  session_storage_.replace(session);
}

void session_builder::update_session(const frame_ptr &frame) {
  if (live_sessions_.find(frame->source()) == live_sessions_.end()) {
    return;
  }
  Session &session = live_sessions_.at(frame->source());
  session.end_time = frame->gen_time();
  session.frame_count++;
  session.data_size += frame->frame_length();
}

void session_builder::rebuild_index_db() {
  std::unordered_map<uint32_t, location_ptr> locations = {};
  auto locator = io_device_->get_locator();
  auto reader = io_device_->open_reader_to_subscribe();
  for (const auto &location : locator->list_locations("*", "*", "*", "*")) {
    SPDLOG_TRACE("investigating journal for [{:08x}] {}", location->uid, location->uname);
    locations.emplace(location->uid, location);
    for (const auto dest_uid : locator->list_location_dest(location)) {
      reader->join(location, dest_uid, 0);
    }
  }
  session_storage_.remove_all<Session>();
  while (reader->data_available()) {
    auto frame = reader->current_frame();
    auto uid = frame->dest() == 0 ? frame->source() : frame->dest();
    if (locations.find(uid) == locations.end()) {
      SPDLOG_WARN("location not found {:08x}", uid);
      reader->next();
      continue;
    }
    auto location = locations.at(uid);
    try {
      if (frame->msg_type() == SessionStart::tag) {
        open_session(location, frame->gen_time());
      } else if (frame->msg_type() == SessionEnd::tag) {
        close_session(location, frame->gen_time());
      } else if (location->category != category::SYSTEM or location->group != "master") {
        update_session(frame);
      }
    } catch (const std::exception &ex) {
      SPDLOG_ERROR("problematic frame at {}, {}", location->uname, ex.what());
    }
    reader->next();
  }
  for (const auto &pair : live_sessions_) {
    session_storage_.replace(pair.second);
  }
}
} // namespace kungfu::yijinjing::index