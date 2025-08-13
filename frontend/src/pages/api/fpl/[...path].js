// File: frontend/src/pages/api/fpl/[...path].js
export default async function handler(req, res) {
  const { path } = req.query;
  const fplApiUrl = `https://fantasy.premierleague.com/api/${path.join('/')}`;

  try {
    const response = await fetch(fplApiUrl);
    if (!response.ok) {
      return res.status(response.status).json({ message: 'Error fetching from FPL API' });
    }
    const data = await response.json();
    res.setHeader('Cache-Control', 's-maxage=300, stale-while-revalidate'); // Cache for 5 minutes
    return res.status(200).json(data);
  } catch (error) {
    return res.status(500).json({ message: 'Internal Server Error' });
  }
}