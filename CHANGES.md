# Changelog #

## Unreleased 0.5.0 ##

### Added ###

* Added option to leave removed post unlocked.
* Added 'domainwatch' to add post domains to AutoMod configuration.
* Added Modmailer actor.
* Added logging handler that posts to Discord.

### Fixed ###

* Fixed crashes on replying in archived threads.
* Fixed bad URL escaping in Notifier.

### Changed ###

* Renamed 'wikiwatch' to 'userwatch' for configuration file.
* Changed configuration format.
* Allowed multiple actions on the same target, provided they come from different
  moderators.
* Changed Nuker to a use a buffer that periodically pauses to look for new
  commands. This makes the bot appear more responsive.

### Removed ###

* Removed legacy default configuration loader.
* Removed notifications and removals from database.
