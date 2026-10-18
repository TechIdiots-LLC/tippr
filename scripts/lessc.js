#!/usr/bin/env node
// The contents of this file are subject to the Common Public Attribution
// License Version 1.0 (the "License"); you may not use this file except in
// compliance with the License. You may obtain a copy of the License at
// https://github.com/TechIdiots-LLC/tippr/blob/master/LICENSE.
//
// Software distributed under the License is distributed on an "AS IS" basis,
// WITHOUT WARRANTY OF ANY KIND, either express or implied. See the License for
// the specific language governing rights and limitations under the License.
//
// The Original Code is Tippr.
//
// The Initial Developer of the Original Code is TechIdiots LLC.
// Copyright (c) 2026 TechIdiots LLC. All Rights Reserved.
///////////////////////////////////////////////////////////////////////////////

// Compile a LESS file to CSS on stdout, for the static build ("make static").
//
// tippr's stylesheets need LESS 1.4, but less 1.4's own command-line tool
// prints nothing on current Node.js versions, so this calls the library
// directly. The installer runs it with NODE_PATH pointing at the pinned
// less@1.4.2 install.
//
// usage: node scripts/lessc.js file.less > file.css

const fs = require("fs");
const path = require("path");
const less = require("less");

const file = process.argv[2];
if (!file) {
  console.error("usage: lessc.js file.less");
  process.exit(2);
}

const parser = new less.Parser({
  paths: [path.dirname(file)],
  filename: file,
});

parser.parse(fs.readFileSync(file, "utf8"), (err, tree) => {
  if (err) {
    console.error(`${err.filename}:${err.line}: ${err.message}`);
    process.exit(1);
  }
  let css;
  try {
    css = tree.toCSS();
  } catch (e) {
    console.error(`${e.filename || file}:${e.line || "?"}: ${e.message}`);
    process.exit(1);
  }
  process.stdout.write(css);
});
