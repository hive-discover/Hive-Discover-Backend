const stats = require("./../stats.js")

const express = require('express'),
router = express.Router();

const request = require('request');


router.get('/', async (req, res) => {
    await stats.addStat(req);

    const imageUrl = req.query.url;
    if(!imageUrl)
      {
        // No imageUrl is given
        res.status(404).send({info : "Not found"}).end()
        return
      }
      
      request.get(imageUrl)
        .on("error", () => res.status(404).send("").end())
        .pipe(res)
});
  
router.post('/', (req, res) => {
    const imageUrl = req.query.url;
    if(!imageUrl)
    {
      // No imageUrl is given
      res.status(404).send({info : "Not found"}).end()
      return
    }

    request.post(imageUrl)
      .on("error", () => res.status(404).send("").end())
      .pipe(res)
});

module.exports = router;