<?php
defined('MOODLE_INTERNAL') || die();

$functions = [
    'local_difodscopilot_get_case_manifest' => [
        'classname' => '\\local_difodscopilot\\external\\get_case_manifest',
        'description' => 'Returns an authorised, versioned manifest for one assignment submission.',
        'type' => 'read',
        'capabilities' => 'local/difodscopilot:exportmanifest',
        'ajax' => false,
    ],
];

$services = [
    'DIFODS Copilot Integration' => [
        'functions' => ['local_difodscopilot_get_case_manifest'],
        'restrictedusers' => 1,
        'enabled' => 1,
        'shortname' => 'difodscopilot',
        'downloadfiles' => 1,
        'uploadfiles' => 0,
    ],
];

