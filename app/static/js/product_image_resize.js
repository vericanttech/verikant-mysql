/**
 * Client-side resize before upload (reduces bandwidth; server still validates type/size).
 * PNG (e.g. after rembg) keeps alpha; other types default to JPEG.
 * @param {File} file - Original image from <input type="file">
 * @param {number} maxEdge - Longer side capped to this many CSS pixels (default 480)
 * @param {number} quality - JPEG quality 0–1 (default 0.82); ignored for PNG output
 * @returns {Promise<Blob>}
 */
function resizeImageToBlob(file, maxEdge, quality) {
  maxEdge = maxEdge || 480;
  quality = quality === undefined ? 0.82 : quality;
  var outType = file.type === 'image/png' ? 'image/png' : 'image/jpeg';
  return new Promise(function (resolve, reject) {
    var img = new Image();
    var url = URL.createObjectURL(file);
    img.onload = function () {
      URL.revokeObjectURL(url);
      var width = img.naturalWidth;
      var height = img.naturalHeight;
      if (width > maxEdge || height > maxEdge) {
        if (width > height) {
          height = Math.round((height * maxEdge) / width);
          width = maxEdge;
        } else {
          width = Math.round((width * maxEdge) / height);
          height = maxEdge;
        }
      }
      var canvas = document.createElement('canvas');
      canvas.width = width;
      canvas.height = height;
      var ctx = canvas.getContext('2d');
      if (outType === 'image/png') {
        ctx.clearRect(0, 0, width, height);
      }
      ctx.drawImage(img, 0, 0, width, height);
      if (outType === 'image/png') {
        canvas.toBlob(
          function (blob) {
            if (blob) resolve(blob);
            else reject(new Error('Canvas toBlob failed'));
          },
          'image/png'
        );
      } else {
        canvas.toBlob(
          function (blob) {
            if (blob) resolve(blob);
            else reject(new Error('Canvas toBlob failed'));
          },
          'image/jpeg',
          quality
        );
      }
    };
    img.onerror = function () {
      URL.revokeObjectURL(url);
      reject(new Error('Could not load image'));
    };
    img.src = url;
  });
}
