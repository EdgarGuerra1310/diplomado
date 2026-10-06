<?php
defined('MOODLE_INTERNAL') || die();

$observers = [
    [
        'eventname' => '\\mod_assign\\event\\submission_created',
        'callback' => '\\local_difodscopilot\\observer::submission_changed',
        'priority' => 1000,
    ],
    [
        'eventname' => '\\mod_assign\\event\\submission_updated',
        'callback' => '\\local_difodscopilot\\observer::submission_changed',
        'priority' => 1000,
    ],
    [
        'eventname' => '\\mod_assign\\event\\submission_status_updated',
        'callback' => '\\local_difodscopilot\\observer::submission_changed',
        'priority' => 1000,
    ],
    [
        'eventname' => '\\core\\event\\course_module_completion_updated',
        'callback' => '\\local_difodscopilot\\observer::completion_updated',
    ],
];

