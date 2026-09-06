export default function VehicleCard({ vehicle }) {
  return (
    <article className="vehicle-card">
      <div className="vehicle-media">
        {vehicle.image_url ? (
          <img src={vehicle.image_url} alt={vehicle.name} loading="lazy" referrerPolicy="no-referrer" />
        ) : (
          <div className="vehicle-placeholder"><span>LS</span><small>IMAGE NOT RESOLVED</small></div>
        )}
        <span className="vehicle-role">{vehicle.category}</span>
      </div>
      <div className="vehicle-body">
        <div className="vehicle-title-row"><h3>{vehicle.name}</h3><span className={vehicle.verified ? 'verified-chip' : 'confidence-chip'}>{Math.round((vehicle.confidence || 0) * 100)}%</span></div>
        <p>{vehicle.details || 'Detected in this week’s update.'}</p>
        <div className="vehicle-meta">
          <span>{vehicle.manufacturer || 'Unknown maker'}</span>
          <span>{vehicle.vehicle_class || `${vehicle.source_count || 1} source${vehicle.source_count === 1 ? '' : 's'}`}</span>
        </div>
      </div>
    </article>
  )
}
