// supabase/functions/paymentWebhook.js
import { createClient } from '@supabase/supabase-js'

const supabase = createClient(process.env.SUPABASE_URL, process.env.SUPABASE_SERVICE_ROLE_KEY)

export default async function handler(req, res) {
  if (req.method === 'POST') {
    const { telegram_id, payment_status, order_id, transaction_sum, plan_id } = req.body

    if (payment_status === 'success') {
      // Fetch the subscription plan details
      const { data: planData, error: planError } = await supabase
        .from('subscription_plans')
        .select('duration, price')
        .eq('plan_id', plan_id)
        .single()

      if (planError) {
        return res.status(400).json({ error: planError.message })
      }

      const { duration, price } = planData

      // Compare the transaction sum with the plan price
      if (transaction_sum !== price) {
        // Notify the user or log the discrepancy
        return res.status(400).json({ error: 'Transaction sum does not match the plan price' })
      }

      // Calculate the expiration date based on the current time and plan duration
      const createdAt = new Date()
      const expireAt = new Date(createdAt.getTime() + durationToMilliseconds(duration))

      // Insert subscription record
      const { data: subscriptionData, error: subscriptionError } = await supabase
        .from('subscriptions')
        .insert([
          { telegram_id, plan_id, status: 'active', created_at: createdAt, expire_at: expireAt }
        ])
        .select()

      if (subscriptionError) {
        return res.status(400).json({ error: subscriptionError.message })
      }

      const subscription_id = subscriptionData[0].subscription_id

      // Update payment transaction with subscription_id and transaction_sum
      const { data, error } = await supabase
        .from('payment_transactions')
        .update({ subscription_id, transaction_sum, created_at: createdAt })
        .eq('order_id', order_id)

      if (error) {
        return res.status(400).json({ error: error.message })
      }

      return res.status(200).json({ message: 'Subscription activated and payment recorded successfully' })
    }

    return res.status(400).json({ error: 'Invalid payment status' })
  }

  return res.status(405).json({ error: 'Method not allowed' })
}

function durationToMilliseconds(duration) {
  const dayMatch = duration.match(/(\d+)\s*(день|дня|дней)/i)
  const monthMatch = duration.match(/(\d+)\s*(месяц|месяца|месяцев)/i)

  if (dayMatch) {
    const value = parseInt(dayMatch[1])
    return value * 1000 * 60 * 60 * 24
  }

  if (monthMatch) {
    const value = parseInt(monthMatch[1])
    return value * 1000 * 60 * 60 * 24 * 30 // Approximation for a month
  }

  throw new Error('Invalid interval format')
}
