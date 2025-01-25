<?php
require __DIR__ . '/vendor/autoload.php';

use Pelago\Emogrifier\CssInliner;

$infile = $argv[1];
$outfile = $argv[2];

$html = file_get_contents($infile);

$visualHtml = CssInliner::fromHtml($html)->inlineCss()->render();

file_put_contents($outfile, $visualHtml);

?>

