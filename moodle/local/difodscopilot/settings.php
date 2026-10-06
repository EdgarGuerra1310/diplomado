<?php
defined('MOODLE_INTERNAL') || die();

if ($hassiteconfig) {
    $settings = new admin_settingpage('local_difodscopilot', get_string('pluginname', 'local_difodscopilot'));
    $ADMIN->add('localplugins', $settings);
    $settings->add(new admin_setting_configtext(
        'local_difodscopilot/apiendpoint',
        get_string('apiendpoint', 'local_difodscopilot'),
        get_string('apiendpoint_desc', 'local_difodscopilot'),
        'http://api:8000/api/v1/moodle/events',
        PARAM_URL
    ));
    $settings->add(new admin_setting_configpasswordunmask(
        'local_difodscopilot/webhooksecret',
        get_string('webhooksecret', 'local_difodscopilot'),
        get_string('webhooksecret_desc', 'local_difodscopilot'),
        ''
    ));
    $settings->add(new admin_setting_configtext(
        'local_difodscopilot/courseids',
        get_string('courseids', 'local_difodscopilot'),
        get_string('courseids_desc', 'local_difodscopilot'),
        '',
        PARAM_TEXT
    ));
}

