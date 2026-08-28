var BASE = self.location.href.replace(/[^/]+$/, "");
importScripts(BASE + "zxing-wasm-reader.js");

var OPTIONS = {
  formats: ["QRCode"],
  tryHarder: true,
  tryRotate: true,
  tryInvert: false,
  tryDownscale: false,
  maxNumberOfSymbols: 1,
};

ZXingWASM.prepareZXingModule({
  overrides: {
    locateFile: function (path, prefix) {
      if (path.indexOf(".wasm") !== -1) {
        var parts = path.split("/");
        return BASE + "wasm/" + parts[parts.length - 1];
      }
      return prefix + path;
    },
  },
});

self.onmessage = function (event) {
  var data = event.data || {};
  var id = data.id;
  var imageData = data.imageData;
  ZXingWASM.readBarcodes(imageData, OPTIONS)
    .then(function (results) {
      var text = results && results[0] && results[0].text ? results[0].text : null;
      self.postMessage({ id: id, text: text });
    })
    .catch(function () {
      self.postMessage({ id: id, text: null });
    });
};
