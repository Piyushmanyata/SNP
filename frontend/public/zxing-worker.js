var BASE = self.location.href.replace(/[^/]+$/, "");
importScripts(BASE + "zxing-wasm-reader.js");

var LIVE = {
  formats: ["QRCode"],
  tryHarder: true,
  tryRotate: true,
  tryInvert: false,
  tryDownscale: false,
  maxNumberOfSymbols: 1,
};

var PHOTO = {
  formats: ["QRCode"],
  tryHarder: true,
  tryRotate: true,
  tryInvert: false,
  tryDownscale: true,
  maxNumberOfSymbols: 1,
};

var ready = ZXingWASM.prepareZXingModule({
  overrides: {
    locateFile: function (path, prefix) {
      if (path.indexOf(".wasm") !== -1) {
        var parts = path.split("/");
        return BASE + "wasm/" + parts[parts.length - 1];
      }
      return prefix + path;
    },
  },
  fireImmediately: true,
});

ready.then(
  function () { self.postMessage({ ready: true }); },
  function () { self.postMessage({ ready: false }); }
);

self.onmessage = function (event) {
  var data = event.data || {};
  ready
    .then(function () { return ZXingWASM.readBarcodes(data.image, data.photo ? PHOTO : LIVE); })
    .then(function (results) {
      var hit = results && results.find(function (r) { return r.isValid !== false && r.text; });
      self.postMessage({ id: data.id, text: hit ? hit.text : null });
    })
    .catch(function () {
      self.postMessage({ id: data.id, text: null });
    });
};
